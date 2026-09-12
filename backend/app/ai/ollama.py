"""Ollama transport.

Everything runs on the machine, which is the main reason to use it here: student
records never leave the building, so the awkward question of whether a school may
send a child's grades to a third-party API does not arise.

Three behaviours were measured against qwen3:4b rather than assumed, and all are
load-bearing:

1. `think: true` is REQUIRED, not an optimisation. With thinking disabled the
   model writes its reasoning into `content` and emits **no tool call at all**;
   with it enabled the reasoning goes to a separate `thinking` field, `content`
   comes back clean, and the tool call fires. It is also faster (3.0s vs 4.5s on
   the same prompt).
2. The model sometimes emits a tool call as plain JSON in `content` instead of a
   structured `tool_calls` entry, occasionally wrapped in a stray `</think>`.
   `parse_text_tool_calls` recovers those rather than silently losing the turn.
3. The context window is NOT what the model card says. qwen3:4b supports 262k
   tokens, but Ollama runs it at 4,096 unless told otherwise, and overflow is cut
   to about half the window with no error. `num_ctx` is therefore always sent,
   oversize input is refused before sending, and truncation is inferred from the
   token count Ollama reports.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from ..config import get_settings

settings = get_settings()


class OllamaError(RuntimeError):
    """Ollama could not be reached, or refused the request."""


@dataclass
class ChatReply:
    content: str
    thinking: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    recovered_from_text: bool = False
    duration_ms: int = 0
    prompt_tokens: int = 0
    truncated: bool = False


# English prose and JSON average 3-6 characters per token; almost nothing exceeds 8.
# So a prompt of N characters that Ollama reports as fewer than N/8 tokens was cut.
CHARS_PER_TOKEN_CEILING = 8
# Conservative estimate used before sending, to refuse input that cannot fit.
CHARS_PER_TOKEN_FLOOR = 3


def _prompt_chars(messages: list[dict], tools: list[dict] | None, fmt: dict | None) -> int:
    total = sum(len(str(m.get("content") or "")) + len(json.dumps(m.get("tool_calls") or []))
                for m in messages)
    return total + len(json.dumps(tools or [])) + len(json.dumps(fmt or {}))


def looks_truncated(prompt_chars: int, prompt_tokens: int) -> bool:
    """Ollama never reports truncation; infer it from the token count it did report."""
    return prompt_chars > 8000 and 0 < prompt_tokens < prompt_chars / CHARS_PER_TOKEN_CEILING


def _post(path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        settings.ollama_url.rstrip("/") + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise OllamaError(f"Ollama returned {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise OllamaError(
            f"Cannot reach Ollama at {settings.ollama_url}. Is it running? ({e})"
        ) from e


def _get_json(path: str, timeout: float) -> dict:
    req = urllib.request.Request(settings.ollama_url.rstrip("/") + path)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        raise OllamaError(f"Cannot reach Ollama at {settings.ollama_url}: {e}") from e


def installed_models() -> list[str]:
    return [m.get("name", "") for m in _get_json("/api/tags", 5.0).get("models", [])]


def model_capabilities(model: str) -> list[str]:
    """A model without `tools` cannot be an agent, however good its prose."""
    try:
        return _post("/api/show", {"model": model}, 15.0).get("capabilities", []) or []
    except OllamaError:
        return []


def health() -> dict:
    """Everything the UI needs to explain why the fleet can or cannot run."""
    try:
        models = installed_models()
    except OllamaError as e:
        return {"reachable": False, "error": str(e), "models": [],
                "model": settings.ollama_model, "can_run_agents": False}
    caps = model_capabilities(settings.ollama_model) if settings.ollama_model in models else []
    return {
        "reachable": True,
        "error": None,
        "url": settings.ollama_url,
        "model": settings.ollama_model,
        "models": models,
        "model_installed": settings.ollama_model in models,
        "capabilities": caps,
        "can_run_agents": "tools" in caps,
    }


_JSON_CALL = re.compile(
    r'\{\s*"name"\s*:\s*"(?P<name>[A-Za-z0-9_]+)"\s*,\s*"arguments"\s*:\s*(?P<args>\{.*?\})\s*\}',
    re.S,
)


def strip_thinking(text: str) -> str:
    """Remove <think> blocks and stray closing tags the model sometimes leaks."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return text.replace("<think>", "").replace("</think>", "").strip()


def parse_text_tool_calls(content: str) -> list[dict[str, Any]]:
    """Recover tool calls the model wrote as prose instead of emitting properly."""
    out: list[dict[str, Any]] = []
    for m in _JSON_CALL.finditer(content or ""):
        try:
            args = json.loads(m.group("args"))
        except json.JSONDecodeError:
            continue
        if isinstance(args, dict):
            out.append({"function": {"name": m.group("name"), "arguments": args}})
    return out


def chat(messages: list[dict], tools: list[dict] | None = None,
         model: str | None = None, timeout: float | None = None,
         fmt: dict | None = None) -> ChatReply:
    """`fmt` is a JSON schema. Ollama constrains decoding to it, which turns
    "the model must remember to call a tool" into "the model must fill in a
    shape" — the difference between unreliable and reliable at this size."""
    chars = _prompt_chars(messages, tools, fmt)
    if chars / CHARS_PER_TOKEN_FLOOR > settings.ollama_num_ctx:
        raise OllamaError(
            f"Input of {chars:,} characters may not fit the {settings.ollama_num_ctx:,}-token "
            "context window, and Ollama would silently cut it. Split it, or raise HR_OLLAMA_NUM_CTX.")
    body: dict[str, Any] = {
        "model": model or settings.ollama_model,
        "stream": False,
        "think": True,                       # see module docstring — required for tool calls
        "messages": messages,
        "options": {"temperature": settings.ollama_temperature,
                    "num_ctx": settings.ollama_num_ctx},
    }
    if tools:
        body["tools"] = tools
    if fmt:
        body["format"] = fmt
    data = _post("/api/chat", body, timeout or settings.ollama_timeout)

    msg = data.get("message", {}) or {}
    content = strip_thinking(msg.get("content") or "")
    calls = msg.get("tool_calls") or []
    recovered = False
    if not calls and content:
        calls = parse_text_tool_calls(content)
        recovered = bool(calls)
    prompt_tokens = int(data.get("prompt_eval_count") or 0)
    return ChatReply(
        content=content,
        thinking=(msg.get("thinking") or "")[:4000],
        tool_calls=calls,
        recovered_from_text=recovered,
        duration_ms=int(data.get("total_duration", 0) // 1_000_000),
        prompt_tokens=prompt_tokens,
        truncated=looks_truncated(chars, prompt_tokens),
    )
