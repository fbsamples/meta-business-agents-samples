---
name: mba-onboarding
description: Take a Meta Business Agent from a PRD to a configured, tested, live agent on a
  WhatsApp Business phone number. Checks the setup is ready, onboards the agent, loads knowledge,
  authors skills, wires connectors, tests before exposure, and rolls out behind an allowlist. Use
  when someone says "set up the agent", "onboard to MBA", "upload these FAQs", "wire up the order
  API", "configure the agent", "why is the agent not responding", or has a PRD and needs a working
  agent. NOT for writing the PRD itself, which is mba-prd-builder.
---

# mba-onboarding

Configure a Meta Business Agent against the public Meta Business Agent Platform API.

The agent you are configuring talks to real customers. There is no sandbox. Every rule below exists
because of that.

## Triage — ask these first, every time

Even if the user gave a specific request, confirm these before touching anything. They take one
minute and prevent hours of backtracking.

**Q1 — Who is this for?**
> "Are you setting this up for your own business, or for a client?"

- **Own business** → go to Q3
- **Client** → Q2

**Q2 — Whose credentials? (only if Q1 = client)**
> "Will you use the client's credentials (their app and token), or your own app to manage multiple
> clients?"

- **Client's credentials** → go to Q3
- **Own app** → read `references/setup.md`: use a Business Integration System User (BISU)
  token for client accounts, as described in the public credentials guide. If documented
  permissions are present but data remains empty, ask the operator to contact their Meta
  representative to confirm app access. This kit promises no processing time. Then go to Q3.

**Q3 — Existing app on the number? (ask everyone)**
> "Is there already an app or tool handling conversations on this WhatsApp number — like a live chat
> platform, CRM, or helpdesk?"

- **Yes** → note it. Surface `references/thread-control.md` now — webhook setup must happen before
  the agent goes live. Then go to Q4.
- **No** → go to Q4.

**Q4 — Do you have a PRD?**
> "Do you have a requirements document or PRD for this agent?"

- **Yes** → go to Q5.
- **No** → offer: "I can either help you build one with `mba-prd-builder` first (recommended — it
  structures the requirements and generates a starter `agent.yaml`), or we can proceed and I'll ask
  the same questions as we go. Which do you prefer?"

**Q5 — Are credentials in `.env`?**
> "Do you have your system user access token and phone number ID ready in `.env`?"

- **Yes** → proceed to Stage 1.
- **No** → read `references/setup.md` and walk through it:
  1. Guide them to create a Meta Developer App and add WhatsApp (if no app yet)
  2. Guide them to generate a system user token in Business Settings
  3. Tell them: "Open `.env` in a text editor (`open -e .env` on macOS or `nano .env`) and add:
     ```
     MBA_TOKEN=your_token_here
     MBA_ENTITY_ID=your_phone_number_id
     ```
     The phone number ID is in WhatsApp Manager → Account tools → Phone numbers → ID column."
  4. Ask them to confirm it's saved, then proceed to Stage 1.

Never read `.env` yourself and never ask the user to paste their token into the conversation.

---

## Rules that apply everywhere

Read `references/api-contract.md` before the first call of a session. In short:

- **Read the reference page before calling an endpoint you have not called in this session.** The
  `openapi/` directory carries the full specs; `api-contract.md` tells you which file to read.
- **Every mutating call is read, then diff and confirm, then write, then verify by re-reading.** A
  `2xx` is not confirmation. A write can succeed and the object still be absent from later reads.
- **Never retry a failed write automatically.** Surface it and let the operator decide.
- **Never handle a secret.** Secrets go in `.env`. Connector secrets may use `${VAR_NAME}`
  only as an entire supported `auth_config` credential value; never interpolate platform
  credentials or secrets into business content, URLs or descriptions. The assistant never reads `.env`.
- **Use the API version from each endpoint's public reference.** Meta Business Agent Platform
  calls use `X-API-Version: 2.0.0`; the Thread Control Cloud API uses `1.0.0`. Do not apply the
  platform header indiscriminately to Cloud API calls.

## The stages

Run them in order. The order is the safety mechanism.

### 1. Preflight

Run `mba doctor`. It checks credentials, eligibility, Terms of Service acceptance, onboarding
status, and the go-live gate. Fix everything it reports before continuing — exit 3 means a person
must act (accept terms, generate a token, grant access). Tell them exactly what to click.

Read `references/preflight.md` for the full check sequence, what each failure means, and who fixes
it. Report what is missing rather than working around it: every prerequisite is something only the
account owner can fix, and discovering a missing one at stage 5 wastes days.

### 2. Match to a template

Ask what the agent is for. If a template fits, use it — it gives you working skills, a connector
contract, a mock backend, and eval scenarios instead of starting from scratch:

> "What is this agent for? There's a ready template for post-purchase support — order status,
> returns, and refunds. Does that match, or are we building from scratch?"

- **Post-purchase** → `mba init --template post-purchase`. Read `templates/post-purchase/README.md`
  for the connector contract, then interview the user to replace every TODO in `agent.yaml` and
  `faqs.yaml`. See `references/connectors.md` for the mock backend setup.
- **Existing agent** → `mba pull` to export the live config to `agent.yaml`, then continue from
  there.
- **Other use case** → start from the closest template and adapt, or build from the PRD directly.

### 3. Onboard and leave it off

Call agent onboarding, then write settings with rollout **disabled**.

```
mba onboard --yes
```

Onboarding creates the agent's configuration slot. Enabling it makes it start answering real
customers. Those are separate steps and everything between them happens with the agent switched off.

Read `references/onboard.md` for settings, the allowlist, and the distinction between the two phone
numbers involved.

### 4. Configure

Knowledge, skills and connectors, in whatever order the PRD supports. Each has its own reference.

Knowledge is usually first because it is the most mechanical and easiest to verify. Connectors are
usually last because they depend on the client's systems being ready, which is the commonest source
of delay.

- `references/knowledge.md` — business info, FAQs, files, websites
- `references/agent-skills.md` — skill authoring, size limits, testing against the PRD
- `references/connectors.md` — connectors, tools, mock backend, credentials, diagnosis

### 5. Test before anyone can reach it

Use `mba eval` to run scripted scenarios. The agent is still disabled — this exercises the full
pipeline without any consumer phone number and nothing is billed.

Read `references/testing.md` for how to write eval scenarios, what to test, and how to interpret
failures. Gated evaluation and launch are currently supported only for unversioned targets;
versioned targets are refused because public API responses do not verify experiment coverage.
Do not substitute a one-off test or an undocumented endpoint to bypass this limitation.

### 6. Go live behind an allowlist

Order matters. The wrong order exposes a half-built agent to real customers.

1. Add testers to the allowlist.
2. Set `ai_audience: ALLOWLISTED_ONLY` and confirm it took.
3. Only then run `mba enable --yes`.
4. Test from an allowlisted number.
5. Confirm the agent does **not** answer a number that is not on the list.

Step 5 is the one people skip. It is the only step that proves the restriction works rather than
just proving you wrote a value.

Widen to `EVERYONE` only after the client has seen it working. That is the single highest-
consequence write in this kit — treat it like a deployment.

Read `references/onboard.md` for the full go-live sequence.

### 7. Operate

Iterate on live behaviour, roll back bad changes, send business events, and diagnose failures.

Read `references/operate.md` for rollback, business events, connector logs, and the kill switch.

## If there is an existing app on the number

If `mba-start` flagged an existing app (a helpdesk, CRM, or live chat platform), thread control
is needed before the agent goes live. Read `references/thread-control.md` — webhook setup must
happen before stage 6.

## When something is wrong

Troubleshooting lives next to the thing that broke, in each reference. Two exceptions:

- `references/api-contract.md` carries error handling that applies to every call.
- `references/escalation.md` covers failures that cannot be fixed from outside — when to stop
  debugging and what to send.

## Not for

- **Writing the PRD.** That is `mba-prd-builder`.
- **Anything in the account owner's Business Manager.** Terms of Service, billing and asset access
  are theirs and always need a human.
- **Replacing the API reference.** This skill encodes sequence, judgment and failure modes. The
  published documentation carries the contracts.

## References

| File | Read it when |
|---|---|
| `references/api-contract.md` | Before the first call of a session. Auth, errors, the write pattern, secrets. |
| `references/setup.md` | Before the engagement starts. Access model, getting a token, what to ask the account owner for. |
| `references/preflight.md` | Stage 1, and again first whenever something has stopped working. |
| `references/onboard.md` | Stages 3 and 6. Onboarding, settings, the allowlist, going live. |
| `references/knowledge.md` | Stage 4. Business info, FAQs, files, websites. |
| `references/agent-skills.md` | Stage 4. Skill authoring, size limits, PRD-derived testing. |
| `references/connectors.md` | Stage 4. Connectors, tools, mock backend, credentials, diagnosis. |
| `references/testing.md` | Stage 5, and throughout. Eval scenarios, go-live gate, server-side evals. |
| `references/operate.md` | Stage 7. Rollback, business events, enable/disable, connector logs. |
| `references/thread-control.md` | When an existing app shares the number. Webhook setup, standby, take/release/pass. |
| `references/escalation.md` | When a failure cannot be fixed from outside. What to send and where. |
