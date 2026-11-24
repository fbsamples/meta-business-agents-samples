# Section map: what each section must contain

The working index for filling `../templates/prd-template.md`. The fill logic keys off **section names and numbers**, never character offsets.

Each section below carries two things: the quality bar it has to meet, and the **intake questions** to ask when the fact ledger came back thin for it. Ask a question only when the sources did not already answer it. A PRD built entirely from an interview is a questionnaire; a PRD built entirely from a transcript is full of holes. The point is to extract first and interview the gaps.

An answer from an intake question enters the ledger as `author-supplied`, never as `confirmed`. See `capture.md`.

## Length discipline: prose is capped, tables are not

Read this before the section map, because every instruction below pushes content **in** ("at least one quantified baseline", "notes an engineer can build from", "field-level, not category-level") and nothing pushes it out. Without a counterweight, the honest way to satisfy the bar is to write more.

The discipline is not uniform brevity. It is **prose brevity with table completeness.**

**Prose rules:**

- A prose block is 2 to 4 sentences.
- A caveat earns a line only if it changes what someone does. Otherwise cut it.
- Never restate a scope exclusion inside a flow step. Section 3 owns scope.
- Never split one idea across two paragraphs.
- No standalone caveat paragraphs.

**Tables are exempt, and completeness there is the bar.** The requirements table, the risks table, open questions, entry points, data in and out, and the workback plan are never trimmed to shorten the document. Cutting a requirement row to save space is a defect, not concision.

Cutting prose to this standard shortens a PRD noticeably without losing anything decision-relevant, because what goes is restatement rather than information. The tables come through untouched.

## Owner vocabulary

Owner values are **`Meta`**, the **client's display name**, and **`Both`**. Never the literal string "Customer" as a party: this is a document for one named client, and the Owner column is where someone scans for their own name.

When an implementation partner is on the engagement, they are a fourth value under their own name. `Both` then becomes ambiguous, so name the two parties explicitly instead.

A requirement resting on a `confirmed-unattributed` fact takes `(TBD - <owner>)` rather than a guessed party.

## Readiness gate

- **Sections 1-5** complete by the end of the **discovery phase**.
- **Sections 6-12** complete by the end of the **technical discovery phase**, before build starts.

Both stages are defined in `SKILL.md`. **Readiness goes in the report, never in the document.** It is a process artifact about the engagement, not information the client needs in a product spec.

## Document Header

Seven rows: Customer, Vertical / Region, Engagement ID, Doc Owner, Status, Quick Links, Key Contacts. Status carries the version and date inline. **Engagement ID** is whatever reference your own organisation tracks this engagement under; if there is none, leave it `(TBD)` rather than inventing one.

**"Customer" is the field label here and stays.** Everywhere else the template means a *party*, it takes the client's display name.

**Discovery:** stakeholder discovery, see `discovery.md`. Who are the key contacts, and what is each person's role? Write what you are told. Do not presuppose which organisations are involved or invent role categories.

## 1. Overview / Summary

Three to four sentences. A stranger should finish them knowing who the customer is, what they want to build, and why it matters. Customer name, vertical, geography. Key scale numbers: revenue, users, catalog size, fleet size. Current state of their messaging or AI channel.

Scale numbers are the most commonly fabricated content in a PRD. Every one needs a citation or `(TBD)`.

**Discovery:** pre-call research. Scale numbers mostly come from research rather than the call: if you can look it up, do not spend discovery time on it. **Market / country** should be confirmed at the very start of the engagement and recorded here — it determines payment methods, language, local data fields, and regulations.

## 2. Problems to Solve

Two labelled blocks, each with concrete data points rather than assertions.

- **For Users:** the end-user experience today and what is painful about it. Cite specific friction, for example "30-60s latency", "no personalization". Name the channel users are already on.
- **For the Business:** the business outcome the customer is driving. Revenue opportunity, competitor threat, and what the current solution fails to deliver.

Aim for at least one quantified baseline.

**Discovery:** modules **A** (AI maturity), **C** (commerce) and **D** (support operations) in `discovery.md`. The ranked pain points from `capture.md` are the raw material for this section: each one already carries its quantified impact and root cause.

A named competitor threat is legitimate market context when it is the client's own framing.

## 3. Project Goals & Timeline

A three-tier table: Priority, Target Date, Description. No row may be `TBD` in both date and description.

| Priority | Meaning |
|---|---|
| P0 - MVP | Core JTBDs, language, auth model, payment model. Explicit about what is NOT included. |
| P1 - Core Differentiation | Rich UI, authentication, personalization, self-service config. |
| Future / Use Case Expansion | Discussed but not committed. Listed to prevent scope creep. |

**A `P0.5` half-tier is allowed** only when both sides coined it on the call, it sits inside the P family, and section 3 carries a one-line definition of what it means for this engagement, committed versus stretch. Cite it like any other fact. **Avoid milestone shorthand (such as M0 / M1 / M2) that the client would not recognise.** Stick to Pilot / Phase 1 / Phase 2 or whatever both sides agreed to on the call.

Follow the table with a note naming the hard dependency the dates hang on: contract status, legal review, privacy review, or a named dependency. **Name the gate without its terms.**

### Scope

Three bullets, and the third is the one people skip:

- **In scope (P0/P1):** the committed JTBDs in one or two lines.
- **Out of scope, deferred:** postponed capabilities, each naming the stage to revisit.
- **Out of scope, permanent:** excluded capabilities, **each with a reason**.

**Discovery:** module **H** (pilot scoping) in `discovery.md`.

Three things the module does not ask, specific to this section:
- Payment: in-thread, payment link, app switch, in-store, or out of scope entirely?
- What is permanently out of scope, and why? Answer this one even if nothing comes to mind — an empty permanent-exclusion list is usually an unasked question, not an absence.
- Anything discussed but not committed? That is the Future tier, and naming it prevents scope creep later.

## 4. UX Flows

### Entry Points

Table: Entry Point, Priority, Description, Value. Record each entry point's consent basis and message type, utility versus marketing. That pairing is a policy gate, not decoration. Use the channel's own vocabulary — see `integration-patterns.md` before naming any platform surface.

### Flows

One numbered flow per JTBD, roughly 8-15 total. Each flow is a Step / Actor / Action table with API calls named **inline**, for example "GET /endpoint with params".

#### Turns alternate, and a lookup never takes a turn of its own

- Turns alternate.
- A data lookup or API call is named inside the acting party's Action cell and **never occupies a row by itself**.
- A non-user, non-agent participant (a human operator) may take a turn.
- **Two consecutive `Agent` rows is a defect** and is mechanically checkable from the Actor column.

When you find yourself writing two agent rows, the missing user turn is usually the interesting one.

Every flow set must include:

- P0 happy paths: FAQ, core transaction end to end, cancellation or modification.
- P1 flows: authenticated, personalized, richer UI.
- Error and edge cases: invalid input (re-prompt, never reject), API failure (silent retry then graceful degradation), and handoff triggers (user requests a human, repeated loops, frustrated user, out of scope).

A flow with no error path and no handoff path is incomplete regardless of how good the happy path reads.

**Discovery:** modules **C** (commerce, for the purchase journey) and **J** (identity and authentication) in `discovery.md`. Entry points are WhatsApp-specific — use the vocabulary in `integration-patterns.md`.

Three things the modules do not ask, specific to this section:
- What are the top things users will ask for? One flow each.
- Handoff: a text pointer ("contact this number"), or a real in-thread human takeover? These are very different builds, and engagements have deliberately chosen either.
- What should happen when the agent cannot answer, or an API fails?

## 5. Product Requirements

A numbered table, typically 15-25 rows: #, Requirement, Priority, Owner, Notes. Every row needs a priority, an owner, and notes an engineer can build from. "Integrate the API" is not a requirement; the endpoints and the JTBDs they cover are.

Exempt from the prose length rules. Never drop a row to shorten the document.

**Discovery:** no module of its own. This section is derived from sections 3, 4 and 6 rather than asked directly. Ask only for the operational rows people forget: who configures the agent's knowledge, who signs off on in-thread copy, who builds the evaluation set and what the pass bar is, and how the pilot will be measured end to end.

## 6. Technical Architecture & Data In/Out

### Integration Pattern

Two to three sentences answering: who owns the conversation, how the agent reaches the customer's data, and the auth model for P0 versus P1. Name the pattern from the catalog in `integration-patterns.md`.

### Data In, `<Client>` to Meta

Table: Category, Key Fields, Priority, Used For. Field-level, not category-level.

### Data Out, Meta to `<Client>`

Same shape. Auth belongs here, for example `client_id, client_secret -> access_token`.

### Data Principles

State platform commitments only when they appear in the applicable published documentation
or terms. Mark unsupported statements `(TBD - Meta)` rather than inferring storage, retention
or availability guarantees from a sample implementation.

Write instead only what the **integration** does:

- which systems are called and which fields cross the boundary
- who owns the identity mapping, which is normally the client
- what a given phase does **not** exchange, when that is a scoped fact rather than an absolute ("P0 exchanges no `<Client>` account data")

Route handling, retention, and regional privacy statements to confirmed language marked `(TBD)` until finalized before the section is shared. **Do not resolve the gap by writing a more detailed true-but-sensitive version either.** The fix is confirmed language, not fuller disclosure.

**Discovery:** modules **B** (technical architecture) and **J** (identity and authentication) in `discovery.md`.

Two things the modules do not ask, specific to this section:
- Do those APIs exist today, or do they need building? This is the single biggest driver of timeline.
- Which integration pattern does the answer imply? Name it from `integration-patterns.md`.

Questions here that only Meta can answer are not blockers. Route them to section 11 with `Meta` as the owner.

## 7. Success Metrics

A north star, a measurement approach, then the table: Metric, Type, Current Baseline, Target, Measurement. No row may be `TBD` in both baseline and target; `Set from Pilot` is a legitimate target when the baseline is genuinely unknown.

Measurement approach names the design: A/B against a control, matched control, or holdout, with what each group sees and the duration. Anything without a standard definition needs an explicit formula in the Measurement column.

**Discovery:** modules **H** (pilot scoping, for success criteria) and **D** (support operations, for baselines) in `discovery.md`. Baselines also come straight from the ranked pain points in `capture.md`.

Two things the modules do not ask, specific to this section:
- What is the one number that decides whether this worked?
- Is there an incumbent experience to compare against? This answers two questions at once: it is both the control arm and the baseline.

## 8. Staged Launch Plan

Table: Stage, Target Date, Audience, Goal, Exit Criteria, across **Build, Test, Pilot, Production**. Then, per stage:

1. A Go/No-Go checklist: APIs working, knowledge configured, measurement set up, contract signed, end-to-end test passing.
2. A rollback trigger and action, quantified. For example "if completion rate is under 50% or API failure is over 5% after one week, pause traffic."
3. A monitoring cadence.

An unquantified rollback trigger is not a rollback trigger.

**Discovery:** module **H** (pilot scoping) in `discovery.md`.

Three things the module does not ask, specific to this section:
- Who sees it first, and how many of them?
- What has to be true before the next stage opens?
- What would make you turn it off? That answer is the rollback trigger, and it needs a number.

## 9. Sprint-Level Workback Plan

Two-week blocks, each a Deliverable / Owner / Due table, covering technical discovery through Pilot at minimum. Adjust to what the customer actually agreed to rather than copying a default schedule.

## 10. Risks & Dependencies

Table: Risk, Impact (High / Medium / Low), Mitigation. Cover technical and business risks. Every mitigation is concrete and owned. Include a policy-eligibility check for the vertical and the message types in play.

**Discovery:** modules **E** (privacy and compliance) and **F** (regional) in `discovery.md`. The fit assessment in `capture.md` already records prerequisites and risks per capability; those become rows here.

One thing the modules do not ask: what could stop this shipping? Review cycles — privacy, legal, infosec, brand — are the most commonly underestimated dependency and the most commonly omitted risk row.

## 11. Open Questions

Split **Technical** and **Product**, each a #, Question, Owner, Status table. An open question with no owner is not tracked, it is decoration.

**This is where an unanswerable intake question goes.** If the author could not answer it and it is a Meta question, it becomes a row here owned by `Meta`. For an author without a platform contact, this section is a deliverable in its own right: a scoped list of exactly what to ask.

Exempt from the prose length rules; keep every row.

## 12. Appendix

Linked supporting material: auth flow diagrams, API spec links, UI mockups, video walkthroughs, full request and response schemas, customer-provided reference materials.
