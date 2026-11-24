# Onboard

Creating the agent, controlling who can reach it, and turning it on.

Two commands are the minimum to get a live agent: onboarding, then settings. Everything else in
this kit is enrichment on top of those two.

## Pull if the agent already exists

Before onboarding, check whether an agent already exists on this number:

```bash
mba doctor
```

If the doctor output shows the agent is already onboarded, export its current config instead of
onboarding again:

```bash
mba pull
```

This writes the live agent state to `agent.yaml`. Work from there rather than starting from scratch.
If the agent is already **enabled**, say so plainly — it is live and talking to real customers, and
every subsequent write changes a production system.

## Create it and leave it off

```bash
mba onboard --yes
```

Onboarding prepares the agent's configuration slot. Settings is what makes it start answering real
customers. **Keep those two moments apart.** Everything between them — knowledge, skills, connectors,
testing — happens with the agent switched off.

If onboarding says the agent already exists, run `mba doctor` and `mba pull`. You are working on a
configured agent and possibly a live one.

## What settings controls

Persona, language, audience, handoff policy, followup policy, and the rollout switch. The
`openapi/settings.yaml` spec carries the field list and enums; read it before writing.

Two fields carry more weight than the rest:

- **`rollout.enabled`** — whether the agent responds to anyone at all. This is also the kill switch.
- **`ai_audience`** — who it responds to. Defaults to `EVERYONE`.

Edit these in `agent.yaml`, then:

```bash
mba plan
mba apply --plan-id <id from plan> --yes
```

## The allowlist trap

**Two different phone numbers are involved — do not confuse them:**

| | What it is | Example |
|---|---|---|
| `MBA_ENTITY_ID` | The **business** number the agent runs on | `your_phone_number_id` |
| Numbers on the allowlist | The **consumer** WhatsApp numbers that will chat with the agent during testing | `+14155550100` |

The allowlist controls which consumer numbers the agent will reply to. It has nothing to do with
the business number.

**Adding people to the allowlist does not restrict anything on its own.**

The allowlist is only consulted when `ai_audience` is `ALLOWLISTED_ONLY`. The default is `EVERYONE`
— an agent enabled without changing it answers every consumer who messages the business.

| `ai_audience` | Who the agent answers |
|---|---|
| `EVERYONE` (default) | All consumers. The allowlist is ignored entirely. |
| `ALLOWLISTED_ONLY` | Only consumers on the allowlist. |

Add testers to the allowlist in `agent.yaml`:

```yaml
allowlist:
  - "+14155550100"
  - "+14155550101"
```

Then `mba plan` → `mba apply --plan-id <id> --yes` after explicit confirmation.

If your number is versioned, stop at the gate: this prototype cannot verify experiment coverage
using the supported public API. Neither changing an audience nor a prior rollback clears that
limitation.

## Going live

The order is the safety mechanism. The wrong order exposes a half-built agent to real customers.

1. **Add every tester** to the allowlist in `agent.yaml`. Apply and read back.
2. **Set `ai_audience: ALLOWLISTED_ONLY`** in `agent.yaml`. Apply and confirm it took.
3. **Only now enable:**

   ```bash
   mba enable --yes
   ```

4. **Test the agent** — see below for which path applies to your number.
5. **Send a message from a number that is NOT on the allowlist** and confirm the agent does not
   answer. This is the step people skip, and it is the only one that proves the restriction works.

### Test path A — production-eligible number

If your number can receive messages from real consumer phones: send a WhatsApp message to the
business number from an allowlisted phone. The agent should reply in the thread.

### Test path B — test/developer number

If the number is not reachable from real consumer phones (shows "invite to WhatsApp" or similar),
use the test command instead. It runs the full agent pipeline, is not billed, and works while the
agent is still disabled:

```bash
mba test "Hi, I want to check my order status"
```

Continue a conversation with `--conversation-id`:

```bash
mba test "What about order 1002?" --conversation-id <id from previous response>
```

This is the primary testing tool for validating agent behaviour before a production number is in
place. See `references/testing.md` for systematic testing.

## Widening the audience

Only after the account owner has seen it working on their own number, and only as an explicit
decision — not a tidy-up at the end of a session.

Set `ai_audience: EVERYONE` in `agent.yaml`, then review the plan and explicitly confirm:

```bash
mba plan
mba apply --plan-id <reviewed-id> --yes --widen-audience
```

For an enabled agent, this also requires a complete passing evaluation of its current
configuration and canonical suite. Behavior changes require disabling first, then applying,
evaluating and enabling again. `--widen-audience` is a confirmation, not a gate bypass.
If enabling with an `EVERYONE` audience, use `mba enable --yes --widen-audience`.

## Turning it off

```bash
mba disable --yes
```

That is the kill switch. It takes effect for new conversations immediately. Disabling does not clear
any configuration — knowledge, skills and connectors survive, so re-enabling resumes the previous
behaviour.

## When it goes wrong

| Symptom | Likely cause |
|---|---|
| `mba doctor` fails credentials | `MBA_TOKEN` or `MBA_ENTITY_ID` not set in `.env` |
| 403 mentioning Terms of Service | Account owner has not accepted them in WhatsApp Manager |
| 403 otherwise | Missing scopes, or the token does not cover this account. Check `debug_token`. |
| Onboarding says the agent exists | It does. Run `mba doctor` and `mba pull`. |
| Agent enabled but silent | Check billing first, then eligibility. |
| Agent answers numbers not on the allowlist | `ai_audience` is `EVERYONE`. The allowlist was never in force. |
