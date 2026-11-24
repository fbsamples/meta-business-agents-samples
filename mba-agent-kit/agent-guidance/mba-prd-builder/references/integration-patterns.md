# Integration patterns, entry points, and channel vocabulary

Vocabularies for sections 4 and 6. Use them rather than inventing terms. A PRD that names its integration pattern from the catalog below is legible to whoever builds it; one that describes the same architecture freehand is not.

Nothing here is content to paste into a PRD. A value belongs in the document only when it is genuinely true of your engagement, and it still needs a citation in the ledger like any other fact.

## Before naming any platform surface

This skill is for **WhatsApp only**. All vocabulary below is WhatsApp-verified. Do not invent or
import terms from other channels. If a source mentions Instagram Direct, Messenger, or another
surface, note it as out of scope rather than attempting to describe it here.

## Integration pattern catalog (channel-neutral)

Feeds section 6. Name the pattern explicitly in the Integration Pattern paragraph. A phased engagement often uses a different pattern per phase, so name each one.

| Pattern | Who owns the conversation | How the agent reaches client data | Auth model | What drives the timeline |
|---|---|---|---|---|
| **Feed-backed, no runtime integration** | the agent | no runtime call to a client system; uses a catalog configured through documented product setup, plus business info and FAQs | no runtime backend credentials; catalog setup follows its own public requirements | catalog quality and coverage; estimate the timeline from the actual project |
| **Direct API-as-tools at runtime** | the agent | calls the client's APIs live, one tool per endpoint | service-level for P0, end-user auth if account data is in scope | whether those APIs exist today, which is the single biggest driver of the whole plan |
| **Handoff / A2A** | the agent upstream, the client's system or agent downstream | qualifies upstream and passes a context packet across; does not read client data itself | whatever the receiving system requires, agreed as part of the packet contract | the receiving system's readiness and the packet schema both sides sign off |
| **Ownership-split** | split: the client owns all proactive and outbound, the agent is reactive-only on inbound | per the inbound half only | as the inbound half requires | agreeing the boundary, because ambiguity here surfaces late as a scope dispute |
| **Wrapper over verbose client APIs** | the agent | a thin wrapper in front of the client's existing APIs, to cut token and context load | inherited from the wrapped APIs | who builds and hosts the wrapper, which is a real deliverable with a real owner |

Supporting sub-patterns, name them alongside the main pattern where they apply: an event webhook to replace polling, an isolated pilot messaging account, hashed-ID or client-owns-the-mapping identity, a deep-link handoff for checkout, a kill switch back to the incumbent experience.

**State the feed-backed tradeoffs whenever you name it.** Freshness is bound to feed cadence, and anything account-specific, order status, loyalty, purchase or size history, is out of scope until a runtime integration lands. A P0 that omits this reads as a smaller promise than it is.

If a real engagement matches none of these, describe it plainly in prose rather than forcing the nearest label. A mislabelled architecture is worse than an unlabelled one.

## Entry-point taxonomy (**WhatsApp-verified**)

Feeds section 4. Tag each entry point to one type, and record its **consent basis** and **message type**, utility versus marketing. That pairing is a policy gate, not decoration, and a PRD that lists entry points without it has skipped the gate.

**Do not apply types 1, 2, or 3 to a non-WhatsApp channel.** They name WhatsApp template categories and WhatsApp ad destinations.

| # | Type | What it is | Who initiates | Message type |
|---|---|---|---|---|
| 1 | **Reply-to-Utility** | the user replies to a proactive utility or milestone message | business sends, user replies | utility |
| 2 | **Reply-to-Marketing** | the user replies to a marketing or MM-Lite templated message | business sends, user replies | marketing |
| 3 | **CTWA** | click-to-WhatsApp ads, with or without ad-context passthrough | user, by clicking the ad | user-initiated thread |
| 4 | **Organic** | website link, app link, QR, saved contact, a key at a physical point of sale | user | user-initiated thread |
| 5 | **Proactive-Outbound** | business-initiated outreach to existing leads | business | templated, category per the engagement |

The **consent basis** is a per-engagement fact, not a property of the type. For types 1, 2 and 5 the business is initiating, so the row needs the actual opt-in behind it: what the user agreed to, where it was captured, and who holds the record. That comes from the client and gets cited like anything else. For types 3 and 4 the user opens the thread, and the row should still name what the user was shown at the point of entry.

Anything you cannot establish is `(TBD - Meta)` in the table and a row in section 11, not a plausible-sounding default.

## Handoff and thread control (**WhatsApp-verified**)

When a flow includes handoff to a human or to another system, describe control correctly. Thread control as a concept transfers to other channels; the specific WhatsApp surfaces must not be asserted for a channel you cannot source them for.

- While the agent holds thread control, customer messages arrive on the **standby webhook**, and control changes are delivered via `messaging_handovers`.
- Control passes to a third-party or human app, and returns to the agent when that app releases it via the **Thread Control Cloud API** release action.

For a requirements document, you may define illustrative handoff labels such as `CHECKOUT`,
`CUSTOMER_REQUEST` or `MISSING_INFORMATION`. These are sample application labels, not Meta API
reason-code enums. Use only the exact values allowed by the public endpoint specification in
API payloads; do not copy a requirements label into a platform field without checking its contract.

A text pointer ("contact this number") and a real in-thread takeover are different builds with different mechanics. Section 4 has to say which one, and this is where the second one gets specified.

## Component and design limits (**WhatsApp-verified**)

When specifying flows and UI, capture the WhatsApp Cloud API component limits that the flow depends on: quick-reply button count and character limits, list message rows and sections, CTA and URL buttons, interactive component caps, message character limits, and template categories. A flow that exceeds a component limit is not buildable, so the limit belongs in the PRD rather than being discovered at build time.

For a non-WhatsApp channel the principle holds and the numbers do not. Capture that channel's own limits from its documentation, or mark them `(TBD - Meta)`. Never carry these across.

## Naming and white-label

In-thread conversation copy uses the client's own assistant name. Whether the agent identifies itself as powered by Meta Business Agent is the client's choice. For a white-label client the agent never surfaces Meta, the messaging platform, or the underlying tooling to the end user, and the PRD should say so explicitly rather than leaving it to the build.
