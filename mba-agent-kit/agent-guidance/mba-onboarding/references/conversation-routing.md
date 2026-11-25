# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# Conversation Routing

Conversation Routing controls which app receives each message on a WhatsApp phone number. Before
the agent goes live, routing must be configured so customer messages actually reach it. This
document covers what to verify before `mba enable --yes` and what the client's admin must do in
Meta Business Suite.

**Routing is configured by the business admin in Meta Business Suite — not through the MBA API and
not by the partner engineer directly.** The steps here tell you what to verify and what to ask the
client to set.

Public references:
- [Meta Business Agent — Conversation Routing](https://developers.facebook.com/documentation/meta-business-agent/conversation-routing)
- [WhatsApp Conversation Routing overview](https://developers.facebook.com/documentation/business-messaging/whatsapp/conversation-routing/overview)

---

## The routing table

One app is the primary first responder for each entry point. When a message arrives, WhatsApp
delivers it to whoever is primary for that entry point.

| Entry point | Recommended default |
|---|---|
| Service messages (customer types a message) | Agent, if it can handle or hand off any request. Otherwise the existing app (BSP, helpdesk). |
| Click-to-WhatsApp ad replies | Agent. |
| Marketing template replies | Existing app, or Route to Sender. Agent only if it runs every marketing journey on this number. |
| Utility template replies | Existing app, or Route to Sender. Same rule as marketing. |
| Calls | No change. Switching the agent on does not change call routing. |

**Exactly one primary per entry point.** A blank entry point means no app gets the message.

---

## Routing groups

- The **account default** covers every phone number on the WhatsApp Business Account.
- The **alternate routing group** contains only the agent's numbers and has its own routing table.
  Put agent numbers here so BSP-only numbers keep their existing routing.
- There is one alternate routing group per WhatsApp Business Account, shared by all the agent's
  numbers on that account.

---

## Escalation partner and standby

- **Escalation partner** (Thread control): exactly one app that receives handed-off conversations.
  Required when handoff is on. The app must subscribe to the `messaging_handovers` webhook field.
- **Standby**: apps that receive copies of every message but must not reply as primary. Each standby
  app must subscribe to the `standby` webhook field.

**Recommended:** keep the same escalation partner and standby apps in both the account default and
the alternate routing group.

---

## Rules

1. **Configure routing before switching the agent on.** Switching on the agent typically makes it
   the primary for every entry point except calls, with existing apps moving to standby. This often
   does not match your plan — set routing explicitly after switching on and read it back. See the
   [published routing docs](https://developers.facebook.com/documentation/meta-business-agent/conversation-routing)
   for exact behavior on your account configuration.

2. **Do not use the WhatsApp Manager routing switch to disable the agent as a rollback step.**
   Switching off via the WhatsApp Manager routing control on a number shared with other apps may
   hand routing to another app or delete the routing configuration — either way, the previous
   routing is lost. Instead: restore routing from a before-screenshot first, then handle existing
   conversations.

   **Note on `mba disable --yes`:** This command sets `rollout.enabled: false` via the MBA
   settings API. The effect on routing configuration depends on your account setup and may vary.
   Confirm the appropriate emergency-stop procedure for your account with your Meta partner
   contact before you need it.

3. **Screenshot routing before any change.** The screenshot is the rollback target.

4. **Routing is changed in Meta Business Suite only.**
   Path: **Meta Business Suite → Settings → Accounts → WhatsApp accounts → [account] →
   Conversation routing tab**. No API or kit command changes routing.

---

## Before going live: what to confirm

Work through these with the operator before `mba enable --yes`. Anything not confirmed is a risk
that should be documented.

**Routing table**
- [ ] Routing table is agreed and matches the deployment plan.
- [ ] Client admin has set the routing in Meta Business Suite.
- [ ] Routing has been read back after the client's admin saved it and matches the plan.

**Webhook subscriptions**
- [ ] Every standby app is subscribed to the `standby` webhook field.
- [ ] The escalation partner is subscribed to `messaging_handovers`.
- [ ] If the existing app sends messages on this number, its messaging account has a funded payment
  method.

**Eligibility**
- [ ] Every active phone number on the WhatsApp Business Account is eligible for the agent. A
  single ineligible number may block routing configuration saves for the whole account — confirm
  the current behavior with your Meta partner contact or the
  [published routing docs](https://developers.facebook.com/documentation/meta-business-agent/conversation-routing).

**After enabling (before widening to `EVERYONE`)**
- [ ] A live handoff test passes from an allowlisted number: the escalation partner sees
  `control_passed`, a person's reply is delivered, and the agent stays silent for three or more
  subsequent messages.
- [ ] The escalation partner can pass the conversation back to the agent.

---

## Gate conditions

Standard routing steps may not apply in certain account configurations. Stop and confirm with your
Meta partner contact before proceeding if any of these appear to be true.

- **Business Suite Inbox is active** on this account or any linked account. Routing configuration
  may not be available for accounts using the Inbox product.
- **The number is on the WhatsApp Business App** at the same time it is being used with Cloud API
  (coexistence). It may not be placeable in an alternate routing group.

Confirm whether these conditions apply to your specific account with your Meta partner contact.

---

## Rollback

If something goes wrong after the agent goes live:

1. **Restore routing** from the before-screenshot in Meta Business Suite. This stops new messages
   from going to the agent.
2. **Hand back conversations the agent already owns.** Restoring routing alone does not transfer
   conversations the agent is currently handling. Contact your Meta partner contact for the
   hand-back procedure.

Be aware that disabling the agent may have routing side effects that vary by account
configuration. Confirm the appropriate rollback procedure with your Meta partner contact before
going live. Do not rely on disabling the agent as a substitute for restoring routing from your
before-screenshot.

---

## Relationship to thread control

If an existing app shares the number (flagged in triage), read `references/thread-control.md`.
Webhook setup and thread-control configuration must happen before going live. Thread control is
how the agent and the existing app exchange control of individual conversations; routing is how
WhatsApp decides which app a message goes to in the first place.
