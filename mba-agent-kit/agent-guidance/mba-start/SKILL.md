---
name: mba-start
description: Start here for anything to do with building or configuring a Meta Business Agent (MBA).
  Works out where you are and routes you to the right next step. Use when someone is new to this
  kit, says "where do I start", "how do I set up a Meta Business Agent", "I want to build an agent",
  "I want to set up an agent", "what do I need before I begin", "help me get started", or is unsure
  which skill applies. Also use when an agent is already live and misbehaving and it is not clear
  where to look. In this kit, any generic agent-building request routes here first.
---

# mba-start

The front door. Work out where you are, say what happens next, and hand off.

## Greet first

When this skill fires — whether someone says "hi", "where do I start", or anything else — open
with a brief introduction before asking anything:

> Hi! I'm your Meta Business Agent setup assistant. I can help with:
> - **Building a PRD** — turning discovery notes or a brief into a structured requirements document
> - **Setting up and configuring an agent** end to end, from credentials to go-live
> - **Thread control** — making a WhatsApp number work alongside an existing helpdesk or app
> - **Troubleshooting** an agent that is live but not behaving as expected
>
> What are you working on?

Keep the intro to four bullets and one question. The goal is to orient in five seconds and get to
the actual situation.

## Triage — ask in order, stop at the first question that changes the path

**Q1 — Who is this for?**

> "Are you setting this up for your own business, or for a client?"

- **Own business** → skip to Q3
- **Client** → Q2

---

**Q2 — Whose credentials? (only if Q1 = client)**

> "Will you be using the client's credentials — their app and token — or your own app to manage
> multiple clients?"

- **Client's credentials** → continue to Q3
- **Own app** → flag this first:

  > "For client accounts, use a Business Integration System User (BISU) token. Follow
  > developers.facebook.com/documentation/meta-business-agent/get-api-key and its linked
  > BISU documentation. If the documented permissions are present but data is still empty,
  > contact your Meta representative to confirm your app's access. Processing times are not
  > guaranteed by this kit."

  Then continue to Q3.

---

**Q3 — Existing app on the number? (ask everyone)**

> "Is there already an app or tool handling conversations on this WhatsApp number — like a live
> chat platform, CRM, or helpdesk?"

- **Yes** → note it. Thread control will be needed before go-live. Surface
  `../mba-onboarding/references/thread-control.md` early — webhook setup must happen before the
  agent is enabled. Then continue to Q4.
- **No** → continue to Q4.

---

**Q4 — Where in the process? (ask everyone)**

> "Do you have a PRD for this agent, and do you have credentials ready?"

| Situation | Go to |
|---|---|
| No PRD yet | `mba-prd-builder` |
| PRD exists, no credentials yet | `mba-onboarding` — preflight stage |
| PRD and credentials ready | `mba-onboarding` — configure stage |
| Agent is live and something is wrong | `mba-onboarding` — run `mba doctor` first |
| Just exploring what this is | Read on, then stop |

If the situation is described rather than picked, infer it and say which you chose — so it can be
corrected.

## Before anything can be built

Four things must be true. None are yours to fix — they require action by whoever owns the
WhatsApp Business account.

| Prerequisite | Who fixes it |
|---|---|
| The WhatsApp Business phone number is eligible for Meta Business Agent | Account owner — determined by account state |
| The Meta Business Agent Terms of Service are accepted in WhatsApp Manager | Account owner only |
| A payment method is attached (required for go-live, not for testing) | Account owner only |
| You have access to the account and a token with the right scopes | Account owner grants it, you use it |

`mba-onboarding` checks all four via `mba doctor` and reports which are missing and who fixes each.
Run it before promising a date.

## What the kit is

Three skills and a CLI tool covering one job: taking an agent from idea to live on a WhatsApp
Business phone number.

- **`mba-prd-builder`** turns discovery notes or a brief into a structured twelve-section PRD. No
  API calls, no credentials. It produces a document. At the end it generates a starter `agent.yaml`
  from the PRD answers so configuration starts from something filled in rather than blank.
- **`mba-onboarding`** turns that PRD into a configured, tested, live agent using the `mba` CLI and
  the public Meta Business Agent Platform API.
- **`mba-start`** is this file.
- **`mba`** is the CLI tool. It manages `agent.yaml` as the desired state of the agent and applies
  changes via a plan/apply cycle. `mba doctor` checks your setup. Claude drives it on your behalf —
  you do not need to run commands yourself unless you want to.

## Why the PRD comes first

Not bureaucracy. The PRD is the input to configuration: its technical section defines the connectors
and their endpoints, its flows become the agent's skills, and its knowledge sections become FAQs and
business info.

At the end of `mba-prd-builder`, it generates a starter `agent.yaml` from the PRD answers — so
configuration starts from something filled in rather than blank.

You are not blocked without a PRD. You will just answer the same questions one at a time during
configuration instead of once during discovery.

## What this kit does not do

- **Anything inside the account owner's Business Manager.** Terms of Service, billing and access
  grants are theirs and always need a human.
- **Handle credentials.** Secrets go in `.env`. Connector credentials use `${VAR_NAME}` only
  as an entire supported `auth_config` credential field; never put them in business content or
  URLs, and never interpolate `MBA_*` platform values. The assistant never reads `.env`.
  If you are using OAuth, authorization is completed out of band through the connector endpoints.
  Never paste a secret into the conversation.
- **Replace the API reference.** This kit encodes sequence, judgment and failure modes. The
  published documentation at `developers.facebook.com/documentation/meta-business-agent/` carries
  the contracts, and it wins whenever the two disagree.

## One thing worth knowing up front

There is no sandbox. Configuration changes affect an agent that may be talking to real customers.

The kit is built around that: the agent is created switched off, everything is verified by reading
it back, and it goes live behind an allowlist before the audience is widened.
