"""The agent loop, built to survive a small model.

Defences, each earned from an observed failure rather than added speculatively:

* **Argument repair.** A bad call becomes a `tool` message describing what was
  wrong. Observed: `list_items_for_course({"category": "All"})` — wrong parameter
  entirely. The model corrects and continues instead of the run dying.
* **Text-fallback parsing.** qwen3 sometimes writes the tool call as JSON prose.
  Recovered in the transport layer and marked in the transcript.
* **Step and wall-clock caps.** Runs are minutes long, so they are background
  jobs; without caps a confused model loops until something times out.
* **Repeat-call detection.** Small models re-call the same tool with the same
  arguments. The second identical call is answered with a nudge to move on.
* **No writes.** Proposals only.
"""
from __future__ import annotations

import json
import time
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AgentRun, Proposal
from .agents import Agent, FLEET
from .ollama import OllamaError, chat
from .toolkit import ToolError, call

settings = get_settings()


def _preview(value, limit: int = 700) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:limit] + ("…" if len(text) > limit else "")


def run_agent(db: Session, agent: Agent, task: str, run: AgentRun,
              opening: tuple[str, dict] | None = None, scope: dict | None = None) -> AgentRun:
    """`opening` replaces the agent's own first read for this run; `scope` is merged
    into the tool context, so a run about one class cannot propose for another."""
    started = time.time()
    tools_by_name = agent.by_name()
    ctx: dict = {"proposals": [], **(scope or {})}
    seen_calls: set[str] = set()
    nudges = 0
    transcript: list[dict] = []
    tool_errors = 0

    messages: list[dict] = [
        {"role": "system", "content": agent.system},
        {"role": "user", "content": task},
    ]

    # Ground the model in real data before it speaks, so it cannot open by inventing one.
    if opening or agent.opening:
        open_name, open_args = opening or agent.opening
        open_tool = tools_by_name.get(open_name)
        if open_tool is not None:
            try:
                seeded = call(open_tool, open_args, db, ctx)
            except Exception as e:
                seeded = {"error": f"{open_name} failed: {e}"}
            messages.append({"role": "assistant", "content": "",
                             "tool_calls": [{"function": {"name": open_name, "arguments": open_args}}]})
            messages.append({"role": "tool", "content": json.dumps(seeded, default=str)})
            seen_calls.add(open_name + json.dumps(open_args, sort_keys=True, default=str))
            transcript.append({"step": 0, "thinking": "", "said": "", "ms": 0, "seeded": True,
                               "calls": [{"tool": open_name, "arguments": open_args, "ok": True,
                                          "result": _preview(seeded)}]})

    status, error, summary = "done", None, ""

    try:
        for step in range(1, settings.agent_max_steps + 1):
            if time.time() - started > settings.agent_max_seconds:
                error = (f"Stopped after {settings.agent_max_seconds:.0f}s. "
                         "Local inference is slow; raise HR_AGENT_MAX_SECONDS or ask for less.")
                status = "failed"
                break

            reply = chat(messages, tools=agent.tool_specs())
            entry = {"step": step, "thinking": reply.thinking[:1200], "said": reply.content[:1200],
                     "ms": reply.duration_ms, "recovered_from_text": reply.recovered_from_text,
                     "prompt_tokens": reply.prompt_tokens, "truncated": reply.truncated,
                     "calls": []}

            if not reply.tool_calls:
                # Observed failure: the model writes "I propose ordering X and Y" in prose and
                # stops, having recorded nothing. One nudge converts that into real calls; it is
                # far more effective than any amount of up-front prompting on a 4B model.
                if not ctx["proposals"] and nudges < 2 and any(t.proposes for t in agent.tools):
                    nudges += 1
                    entry["nudged"] = True
                    transcript.append(entry)
                    messages.append({"role": "assistant", "content": reply.content})
                    messages.append({"role": "user", "content": (
                        "Nothing was recorded. Describing an action in text does not record it — "
                        "only a tool call does. If you want the actions you just described to "
                        "happen, call the matching propose_ tool now, once per action, using exact "
                        "identifiers from the tool results above. If you have nothing worth "
                        "proposing, reply with the single word NONE.")})
                    continue
                summary = reply.content.strip()
                transcript.append(entry)
                break

            messages.append({"role": "assistant", "content": reply.content,
                             "tool_calls": reply.tool_calls})

            for tc in reply.tool_calls:
                fn = tc.get("function", {}) or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments", {}) or {}
                record = {"tool": name, "arguments": raw_args}
                tool = tools_by_name.get(name)

                if tool is None:
                    tool_errors += 1
                    msg = (f"There is no tool called {name!r}. "
                           f"Available tools: {', '.join(tools_by_name)}.")
                    record |= {"ok": False, "error": msg}
                    messages.append({"role": "tool", "content": json.dumps({"error": msg})})
                    entry["calls"].append(record)
                    continue

                fingerprint = name + json.dumps(raw_args, sort_keys=True, default=str)
                if fingerprint in seen_calls and tool.proposes is None:
                    msg = (f"You already called {name} with those arguments and have the result above. "
                           "Use it, or move on to a proposal or your summary.")
                    record |= {"ok": False, "error": msg, "repeat": True}
                    messages.append({"role": "tool", "content": json.dumps({"note": msg})})
                    entry["calls"].append(record)
                    continue
                seen_calls.add(fingerprint)

                try:
                    result = call(tool, raw_args, db, ctx)
                    record |= {"ok": True, "result": _preview(result)}
                    messages.append({"role": "tool", "content": json.dumps(result, default=str)})
                except ToolError as e:
                    tool_errors += 1
                    record |= {"ok": False, "error": str(e)}
                    messages.append({"role": "tool", "content": json.dumps({"error": str(e)})})
                except Exception as e:                      # a handler bug, not the model's fault
                    tool_errors += 1
                    msg = f"{name} failed internally: {e}"
                    record |= {"ok": False, "error": msg}
                    messages.append({"role": "tool", "content": json.dumps({"error": msg})})

                entry["calls"].append(record)

            transcript.append(entry)
        else:
            summary = summary or ""
            error = (f"Stopped at the {settings.agent_max_steps}-step limit without a final summary. "
                     "Any proposals below are still valid; the agent simply did not wrap up.")

    except OllamaError as e:
        status, error = "failed", str(e)

    # Harvest. A 4B model reliably reads, then reliably *describes* what it wants
    # to do — and unreliably calls the tool that records it. Observed: three steps
    # of prose about proposals, two nudges, zero tool calls. So the last step does
    # not ask it to remember anything; it constrains decoding to a JSON shape and
    # replays each entry through the very same tool handlers, so every guardrail
    # (real SKUs, real students, free rooms, no duplicate plans) still applies.
    proposers = [t for t in agent.tools if t.proposes]
    if status == "done" and not ctx["proposals"] and proposers:
        harvested, harvest_note = _harvest(db, agent, proposers, messages, ctx)
        transcript.append(harvest_note)
        tool_errors += harvested

    run.status = status
    run.summary = summary
    run.transcript = transcript
    run.steps_used = len(transcript)
    run.tool_errors = tool_errors
    run.duration_ms = int((time.time() - started) * 1000)
    run.error = error
    run.finished_at = datetime.utcnow()
    db.add(run)
    db.flush()

    for p in ctx["proposals"]:
        db.add(Proposal(run_id=run.id, agent=agent.name, kind=p["kind"], summary=p["summary"],
                        reason=p.get("reason", ""), payload=p["payload"], evidence=p["evidence"],
                        status="pending"))
    db.commit()
    db.refresh(run)
    return run


def _harvest(db: Session, agent: Agent, proposers: list, messages: list[dict], ctx: dict) -> tuple[int, dict]:
    """Constrained decoding, one proposing tool at a time.

    A generic {"tool": ..., "arguments": {object}} schema was not enough: the
    model filled in a plausible-looking action but dropped `rationale`, which the
    tool requires, so every harvested entry was rejected. Feeding the tool's OWN
    parameter schema to Ollama makes the required fields structurally impossible
    to omit - the grammar will not emit an object without them. One call per
    proposing tool (so one or two per agent), and each result still goes through
    the same handler, so hallucinated identifiers are caught exactly as before.
    """
    note = {"step": "harvest", "thinking": "", "said": "", "ms": 0, "harvest": True, "calls": []}
    errors = 0

    for tool in proposers:
        if len(ctx["proposals"]) >= 3:
            break
        schema = {
            "type": "object",
            "properties": {"actions": {"type": "array", "items": tool.parameters}},
            "required": ["actions"],
        }
        ask = list(messages) + [{"role": "user", "content": (
            "Using only the tool results above, list the " + tool.name + " actions worth "
            "recording, as JSON under \"actions\". " + tool.description + " Use exact "
            "identifiers from the results. Fill in every field. If there is nothing worth "
            "recording, return an empty list.")}]
        try:
            reply = chat(ask, fmt=schema)
            note["ms"] += reply.duration_ms
            note["said"] = (note["said"] + " " + reply.content[:400]).strip()
            payload = json.loads(reply.content or "{}")
        except (OllamaError, json.JSONDecodeError) as e:
            note["calls"].append({"tool": tool.name, "arguments": {}, "ok": False,
                                  "error": "No structured result: " + str(e)})
            errors += 1
            continue

        for args in (payload.get("actions") or [])[:3]:
            if len(ctx["proposals"]) >= 3:
                break
            record = {"tool": tool.name, "arguments": args}
            try:
                call(tool, args, db, ctx)
                record["ok"] = True
            except ToolError as e:
                record |= {"ok": False, "error": str(e)}
                errors += 1
            except Exception as e:
                record |= {"ok": False, "error": type(e).__name__ + ": " + str(e)}
                errors += 1
            note["calls"].append(record)
    return errors, note


def run_in_background(run_id: int, agent_name: str, task: str,
                      opening: tuple[str, dict] | None = None, scope: dict | None = None) -> None:
    """Entry point for FastAPI BackgroundTasks — owns its own session."""
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        run = db.get(AgentRun, run_id)
        if run is None:
            return
        agent = FLEET.get(agent_name)
        if agent is None:
            run.status, run.error = "failed", f"No agent named {agent_name!r}."
            db.commit()
            return
        run_agent(db, agent, task, run, opening=opening, scope=scope)
    except Exception as e:                                   # never leave a run stuck on "running"
        db.rollback()
        run = db.get(AgentRun, run_id)
        if run is not None:
            run.status, run.error = "failed", f"{type(e).__name__}: {e}"
            run.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
