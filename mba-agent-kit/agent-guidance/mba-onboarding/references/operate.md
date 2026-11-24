# Operate

What to do after the agent is live: watch it, fix it, roll back bad changes, and trigger it
proactively with business events.

## The kill switch

```bash
mba disable --yes
```

Stops the agent immediately for new conversations. Use this whenever something is wrong and you
need to stop the bleeding while you investigate. Disabling does not clear any configuration —
knowledge, skills and connectors survive, so re-enabling resumes the previous behaviour.

## Connector logs

```bash
mba logs <connector_name>
```

The first place to look when a live conversation goes wrong. Shows recent tool calls with their
status, failure code, error message, and latency. Also reports success rate and p95 latency over
the recent window.

Read `references/connectors.md` for the failure code taxonomy and who owns each type of fix.

## Config versioning and rollback

The public versioning endpoints list versions, read the active version and set it conditionally.
The kit does not expose a rule-management endpoint. Because the public API cannot establish that
all customers receive the active version, the prototype launch gate blocks versioned targets.
Rollback remains available while disabled, but it does not constitute approval to enable.

```bash
mba versions                          # list recent versions (* marks the active one)
mba disable --yes                     # stop exposure before changing behavior
mba rollback <version_id> --yes       # restore an earlier version while disabled
mba pull --force                      # sync agent.yaml to match what is now configured
```

**After rolling back, always run `mba pull --force`** so `agent.yaml` matches what is live.
Otherwise the next `mba plan` will show the rolled-back changes as pending additions.

**Note:** versioning may not be available on all numbers yet. If `mba versions` returns an empty
list, the number has not been migrated to versioned configuration — rollback is not available until
it is. Use `mba disable --yes` as the immediate fix for a bad change, then re-apply the corrected
config.

## Business events (proactive outbound)

Business events trigger the agent to act in a specific customer conversation — for example, sending
a shipping update when an order ships, or following up after a document is verified.

```bash
mba event send \
  --to "+14155550100" \
  --type "order_shipped" \
  --payload '{"order_number": "1001", "tracking_url": "https://..."}' \
  --yes
```

**Key constraints:**
- The customer must have an **existing conversation** with the business. Business events are not for
  cold outreach — if the customer has never messaged, the event is rejected.
- `--to` accepts the customer's phone number in E.164 format (`+14155550100`) or their
  business-scoped user ID (BSUID) from the webhook — useful when you do not have their phone number.
- `type` is your own identifier (max 256 chars), e.g. `"order_shipped"`, `"document_verified"`.
- `payload` is a JSON string passed through to the agent as-is (max 4096 chars). The agent uses
  it to personalise the message.
- Returns immediately with status `"accepted"` — delivery is asynchronous.

**Check event status:**

```bash
mba event get --id <agent_event_id>
```

Status values: `request_received` → `processing` → `sent` / `success` / `failed` / `skipped`.

**Common failure reasons:**

| `error_message` | Cause |
|---|---|
| `agent_not_enabled` | The agent is turned off. Enable it first. |
| `consumer_not_in_agent_audience` | The customer is not in the audience (allowlist or rollout excludes them). |
| `thread_not_owned_by_agent` | Another app holds thread control. |
| `billing_not_configured` | Payment method missing or account details incomplete. |
| `event_content_rejected` | The event text was declined by content filtering. |

## Widening the audience

After the agent has been tested behind `ALLOWLISTED_ONLY` and the account owner is happy:

1. Set `ai_audience: EVERYONE` in `agent.yaml`.
2. `mba plan` → review → `mba apply --plan-id <id> --yes --widen-audience` with explicit
   go-ahead and a passing evaluation of the current configuration and canonical suite.
3. Watch `mba logs <connector>` for the first hour.

This is the highest-consequence write in the kit. Know how to reverse it (`mba disable --yes` or
roll back to a previous version) before you do it.

## Routine monitoring

- `mba logs <connector>` — check success rate and p95 latency periodically.
- `mba versions` — keep track of which version is live and when it was applied.
- `mba eval` — re-run after any config change to confirm nothing regressed.

When a real conversation goes badly, add it as an eval scenario so it stays fixed:

```bash
# Add a new scenario file to evals/
# Then:
mba eval --only <new_scenario_name>    # test it in isolation
mba eval                               # confirm the full suite still passes
```
