# Testing

Proving the agent works before customers meet it, and understanding what it did afterwards.

## Start with `mba eval`

```bash
mba eval
mba eval -v    # print every transcript
```

`mba eval` runs every scenario in `evals/*.yaml` through the Agent Test API. Each scenario is a
scripted customer conversation. The runs are not billed and never reach real customers, and they
work while the agent is still disabled.

**Not billed does not mean no side effects on connected systems.** If a connector points at a real
API, the agent can call it during a test — `create_return` on a real order system creates a real
return, even inside an unbilled test conversation. Before running evals against a real connector:
- Use the mock backend, or
- Point at a sandbox/staging API, or
- Use read-only credentials that cannot perform writes, or
- Use designated test records that cannot affect real customers, orders, or payments.

Switch to the real API only once you are ready to go live.

**Go-live gate:** a complete passing run must match the selected target, authoritative live
configuration and canonical `evals/` suite beside `agent.yaml`. It must start after the last
successful configuration change. A failed or interrupted apply leaves the gate closed; changes
to the target, configuration or suite invalidate the result. A failed or interrupted newer evaluation
also closes the gate instead of preserving an older passing run.

**Versioned targets are not supported by this prototype's launch gate.** The public API describes
experimental versions but does not provide a supported operation to verify the absence of rules.
The kit refuses gated evaluation, enabling and live widening for those targets. Do not infer that
an active-version response proves all customers receive it, and do not bypass the restriction.
One-off `mba test` and server-side diagnostics are not launch authorization.

## Writing eval scenarios

Each file in `evals/` is one scenario — a list of user turns with optional deterministic checks:

```yaml
name: wismo-with-order-number
turns:
  - user: "Where is my order 1001?"
    expect:
      contains_any: ["shipped", "in transit", "delivered"]
      handoff: false
  - user: "When will it arrive?"
    expect:
      contains_any: ["estimated", "delivery date"]
success_criteria:
  - Agent confirms order status without inventing tracking details
  - Agent does not promise a specific date it cannot verify
```

**Deterministic checks** (`contains_any`, `contains_all`, `not_contains`, `matches`, `handoff`,
`responds`) decide PASS/FAIL automatically.

**`success_criteria`** are for judgment — read every transcript against them yourself and report
any you think fail, with the quote that shows it. Do not weaken a scenario to make it pass unless
the expectation was genuinely wrong.

**Seed scenarios from the PRD.** Section 4 flows are already written down — turning them into eval
cases is transcription. This keeps the thing you measure aligned with what was agreed.

Add a scenario whenever a bad real conversation is reported, so it stays fixed.

## What to test

The happy path is the least likely thing to break in production. Test these too:

- **Each job the agent is meant to do**, one at a time, before combining them
- **Error paths** — connector tool fails, invalid input, answer not in the knowledge base
- **Out of scope** — ask it something it should refuse or hand off
- **Handoff** — whatever the PRD said triggers handoff; check it actually fires
- **Guardrails** — if a skill says never to promise a delivery date, try to make it promise one

**A starting target: 5 passing scenarios with zero critical failures.** Zero critical failures means
no policy violation, no tool misuse, no fabricated IDs or URLs. Once 5 pass cleanly, expand the
suite. The go-live gate requires all scenarios to pass — `mba eval` must complete with no
failures before `mba enable` will run.

## One-off probing

For quick checks during development:

```bash
mba test "Hi, I want to check my order"
mba test "What about order 1002?" --conversation-id <id from previous>
```

Partial runs (`--only`) and runs from a different `--dir` are diagnostic only and do not
satisfy the go-live gate. Only a full run of the canonical `evals/` suite beside the selected
`agent.yaml` does. The suite is fingerprinted, so editing it after a run invalidates approval.

## Server-side evals

Meta generates eval cases for your agent based on its configuration:

```bash
mba eval-remote cases              # list cases Meta generated
mba eval-remote run <id1> <id2>    # start a run (ask before running)
mba eval-remote status <job_id>    # poll until complete
```

Results include per-conversation scores, failure categories, and recommended actions. These
complement your local `evals/` scenarios — run them after your local suite passes.

Requires the documented `whatsapp_business_messaging` permission and access to the
Meta Business Agent Platform API for the selected business number.

## A passing test is not a working agent

Test behaviour and production behaviour are documented as not identical. Treat a green eval as
necessary, not sufficient. Things that reliably differ in production: interactive components
rendering, media fetching, handoff, and anything timing-dependent. Those need a real message from
an allowlisted number, which is why stage 6 exists.

## Understanding what happened

When a conversation produces unexpected behaviour, read these in order:

1. **`mba eval -v`** — full transcript with deterministic check results
2. **`insights/conversations/turns`** — which knowledge and skills the agent drew on per turn
3. **`mba logs <connector>`** — whether a tool fired, what came back, how long it took

Each narrows where the fault is before you look deeper.

**When a scenario fails, identify the layer:**

- **Behavioural failure** — the agent had the right information but reasoned, phrased or acted
  wrongly. Fix the skills.
- **Knowledge gap** — the agent answered from nothing or the wrong source. Add or correct
  knowledge.

Mixing these up leads to editing skills when the problem is missing FAQs, or adding FAQs when the
problem is a contradictory skill.

## The fix loop

```
mba eval → identify failure layer → fix one thing → mba plan → mba apply → mba eval
```

One change at a time. Skills interact, and two changes at once means you learn nothing about either.
When behaviour changes unexpectedly, read everything back and diff against your copies before
changing anything else.
