# AI agents

Halverson Ridge uses small language models running locally through
[Ollama](https://ollama.com). Local inference is a design requirement, not a cost
saving: **student records never leave the school's hardware**, so the question of
sending a child's grades to a third-party API does not arise.

The architecture assumes the model is unreliable, not that it is small. A larger
tool-capable model is the single highest-leverage upgrade; the guardrails stay
the same and the proposals get better.

- [The fleet](#the-fleet)
- [Agents propose; people approve](#agents-propose-people-approve)
- [What the model does wrong, measured](#what-the-model-does-wrong-measured)
- [Transcripts](#transcripts)
- [How runs execute](#how-runs-execute)
- [Running the agents locally](#running-the-agents-locally)

## The fleet

| Agent | Module | Reads | Can propose | Who can use it |
|---|---|---|---|---|
| Student support | core | flagged students, strands | a support plan | counselor, admin |
| Class improvement | core | class performance | a class improvement plan | counselor, admin |
| Study plan | core | one student's work in one class | a study plan | counselor, admin (teachers can request drafts) |
| Registrar | `registrar` | sections, rooms, waitlists | open a section, change capacity | registrar, admin |
| Stockroom | `stockroom` | inventory, what classes consume | order stock, change a reorder point, stock a new item | business office, admin |
| Finance | `finance` | budget lines, charges | revise the budget, open a line, hold a charge | business office, admin |
| General manager | `manager` | a school-wide briefing | nothing: it dispatches the others | admin |

A role can see an agent's runs, transcripts and proposals only if it may use that
agent, because a transcript quotes the records it read.

## Agents propose; people approve

An agent has read tools for its own area and `propose_*` tools that record an
intent. **Nothing reaches the database until a person approves it.** Approval
runs deterministic code (`app/ai/executor.py`) that re-validates against current
state: a seat that filled, or a plan opened since the proposal was made, is
refused rather than forced through.

- **Approving needs the same permission as making the change by hand.** A
  counselor cannot approve a budget transfer.
- **Rejecting requires a reason.** Reasons are stored with the decider and,
  read together, show where the agents or the indices go wrong.
- **The decider is recorded** on the proposal and in the audit log.

In testing, the model invented a SKU and an enrollment count. Neither reached
the database: the proposal tool rejected the unknown SKU with a message telling
the model how to recover, and it corrected itself on the next step.

## What the model does wrong, measured

`ollama show` is the gate: an agent needs the `tools` capability. `gemma3:1b`
cannot call tools at all; `qwen3:4b` can. Four behaviors of `qwen3:4b` were
measured rather than assumed, and each is handled in the code:

1. **`think: true` is required.** With thinking disabled the model writes its
   reasoning into the reply and emits no tool call. With it enabled the call
   fires, and faster (3.0s vs 4.5s).
2. **It gets arguments wrong.** Every call is schema-checked, and a failure is
   returned as a tool message naming what was wrong, so the model repairs it
   instead of the run dying.
3. **It describes actions instead of taking them.** Two defenses. The runner
   performs the agent's first read itself (a *seeded opening read*), so the model
   cannot open by inventing data. And a *nudge* follows a turn that ends in prose
   with no proposals.
4. **It sometimes writes a tool call as prose JSON.** A fallback parser recovers
   it and flags it in the transcript.

As a backstop, a run that still ends with no proposals gets a **harvest** step:
one more call with Ollama's constrained JSON decoding, using the proposing tool's
own schema, so the final question is "fill in this shape". Every harvested entry
goes through the same tool handlers, so every guardrail still applies.

Runs are also capped by steps (`HR_AGENT_MAX_STEPS`) and wall-clock time
(`HR_AGENT_MAX_SECONDS`), and a repeated identical tool call is answered with a
nudge to move on.

**Observed on the finance agent.** Given both a single-transfer tool and a
revision tool, with five budget lines short, the model funded one line and
stopped. With only the revision tool, the same sweep proposed one revision
covering all five lines. That is why the agent has no single-transfer tool.

## Transcripts

The only basis for trusting a proposal from an unreliable model is being able to
read exactly what happened. Every run keeps its whole transcript: each step,
each tool call and its arguments, each rejection and why, whether a nudge or the
harvest was needed, and what the agent concluded. The Agents tab shows it all.

## How runs execute

Agent runs are **jobs**, run by the worker process, not by the web server
(see [deployment](deployment.md#background-jobs)):

- Starting a run records it as `queued` and returns immediately.
- The worker runs one model-bound job at a time, so Ollama serves one request.
- A run whose worker dies is retried, and marked failed after its last attempt.
- The interface polls while a run is queued or running.

A typed task steers the run. Told *"only look at Science Lab items"*, the
stockroom agent saw all ten low items in its opening read and proposed only the
two Science Lab ones.

### The general manager

The general manager (the `manager` module, administrators only) has no propose
tools. It answers questions from a computed school-wide briefing: a small model
asked to summarize raw tables drops and invents figures, but handed a correct
digest it quotes it. It can also **dispatch** specialists with tasks it writes.
That needs no approval, because a specialist can itself only propose. It is
limited to three dispatches per run, never itself, and never to a busy agent.

## Running the agents locally

```bash
ollama serve
ollama pull qwen3:4b
./dev.sh                # starts the API, the worker and the interface
```

Use `HR_OLLAMA_MODEL` for a different model and `HR_OLLAMA_URL` for Ollama on
another machine. If the model is missing or cannot call tools, the interface says
so and disables the run buttons rather than failing at run time.

The agent layer is tested without calling Ollama. The tests cover argument
validation and repair messages, refusal of invented identifiers, the proposal
boundary (no tool may write to the database), the executor's staleness checks,
and route behavior when the model is unavailable.
