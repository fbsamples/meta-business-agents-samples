# Capture: sources, the fact ledger, and citations

Everything in this file produces **working artifacts you keep on your own side**. None of it ships. The fact ledger, its locators, its speaker labels, and its source keys stay out of the client-facing document.

Build the ledger before you write any prose. The PRD is then a rendering of the ledger, and every line in it has somewhere to point back to.

## Illustrative examples

All example companies, dates, volumes, version numbers, recordings, timestamps and fact rows
below are fictional. They demonstrate the format; they are not records of a client engagement.
Replace them with authorized sources in your own private working ledger.

## 1. What counts as a source

A source is a record you can **re-open in full** at the moment someone challenges a line in the PRD. Your memory of a call is not a source. A colleague's summary of a call you did not attend is a source for what the summary says, never for what was said on the call.

| Source | Good for | Caveat |
|---|---|---|
| Your own notes from a client call | Everything, if the note is specific | A paraphrase cannot support a quoted number |
| A recording or transcript of a call you ran and hold | Sections 1-8, quoted numbers | Only if you were authorised to record it and you still have it |
| Email and message threads with the client | Commitments, dates, named contacts | Quote the thread, not the recollection of it |
| RFP, tender, or written brief | Sections 2, 3, 5, 7 | Often aspirational; it states what the client asked for, not what was agreed |
| Discovery deck or workshop output | Sections 1-4 | Note who authored it, you or the client |
| The client's own API documentation, sandbox spec, or collection | Section 6, field level | Version it; a doc without a version is a moving target |
| The client's public material, site, app, pricing page | Section 1 scale numbers | Dated at capture, because it changes under you |

**A source you cannot re-open later cannot be cited, and a fact you cannot cite does not enter the PRD as a fact.** It enters as a gap, or as an open question in section 11.

## 2. The fact ledger

Two tables, kept together, written before any prose.

### Sources table

Assign a short key per source and register it first. Without a key, a locator like `[00:41:12]` is ambiguous across two recordings that both have a 00:41 and overlapping attendees.

| Key | Source | Date | Where it lives | Notes |
|---|---|---|---|---|
| `A12` | Client working session, recording | 2026-08-12 | your engagement folder | shared room device on the client side |
| `J30` | Discovery call, your notes | 2026-07-30 | your engagement folder | |
| `RFP` | Client RFP, v2 | 2026-06-04 | client-supplied | supersedes v1 |
| `APIDOC` | Client order API reference | 2026-07-22 | client developer portal | v3.1 |

### Fact table

One row per fact. Every row carries all five columns.

| Fact | PRD section | Status | Owner | Citation |
|---|---|---|---|---|
| Catalog is roughly 50K SKUs, one category for the pilot | 1 Overview | confirmed | `<Client>` | `[J30 00:41:57] <name>` |
| Pilot targets a single brand, not the full portfolio | 3 Goals | confirmed-unattributed | (unset) | `[A12 01:12:26] ROOM` |
| Handoff is a text pointer, not in-thread takeover | 4 UX Flows | author-supplied | `<Client>` | `[intake 2026-08-20]` |
| Auth model for the product API | 6 Technical | pending | `<Client>` | not discussed |

A fact that no source answers still gets a row. **A gap is a row with status `pending` naming whoever owes you the answer**, never a plausible guess dressed as content. That is the ledger's own owner column, which is about who you chase; it is not the same as the PRD's section 5 Owner column, which is about who builds the thing. See below.

## 3. What the ledger rolls up into

The ledger is row-level. After each call, roll those rows up into five artifacts. They are what a
discovery conversation is supposed to produce, and each one feeds the PRD directly.

### Current state map

Systems and tools in use, with vendors and versions where they matter. Data sources, formats and
flows. Team structure and ownership. Volumes and scale: messages per day, SKUs, agents, markets.

Feeds section 1 and section 6.

### Pain points, ranked

One entry per pain point, ordered by how much it matters to the client. Each carries four things:

| Field | Content |
|---|---|
| Description | What is happening |
| Impact | Quantified wherever possible: time, money, CSAT, volume |
| Root cause | Why it is happening |
| Current workaround | How they cope today |

This is the most load-bearing of the five. Section 2 requires at least one quantified baseline and
section 7 requires current baselines for the metrics table; both come from here. A pain point with
no number is a pain point you did not finish asking about.

### Fit assessment

For each capability under consideration: a fit of strong, moderate, weak or none; the specific
evidence from discovery; what must be true for it to work; and what could go wrong.

Prerequisites become section 5 requirements. Risks become section 10 rows.

### Open questions

What you still do not know, stated honestly. These drive the next call, and they become section 11
verbatim. Anything only Meta can answer is owned by `Meta` here and stays owned by `Meta` in the
PRD.

### Next steps

Specific actions, each with an owner and a date. These do not appear in the PRD. They are how you
run the engagement between calls.

## 4. Attribution statuses

| Status | Meaning | May it decide the PRD's section 5 Owner? |
|---|---|---|
| `confirmed` | the client said it, and the speaker is identifiable | yes |
| `confirmed-unattributed` | said on the call, the locator is real, but the speaker label is a shared room device or an unlabelled note | **no** |
| `author-supplied` | you supplied it, from an intake question or your own working knowledge | yes, but see below |
| `pending` | inferred, or simply not discussed | no |

Further rules:

- **Every intake answer enters as `author-supplied`.** It never becomes `confirmed`. Asking yourself a question and writing down your own answer does not make the client have said it, and the whole value of the status column is that it stays true under pressure.
- An `author-supplied` fact that fixes a **date, a price, a volume, or a commitment** also becomes a row in section 11, owned by the client, until they confirm it in writing. Those are the facts that get quoted back at you.
- A `confirmed-unattributed` fact is real content and belongs in the PRD. What it cannot do is decide **which party** owns a requirement.
- Numbers are quoted as said. Do not round, convert, or annualise a number the client gave you.

## 5. Why the status decides the Owner column

Section 5 requires an owner on every requirement. A requirement resting on a `confirmed-unattributed` fact takes **`(TBD - <owner>)`** in the Owner column, resolved with the client, never inferred. That is a complete answer to the section 5 bar, and a guessed party is not.

Never infer a party from conversational tone and then present it as confirmed. If the transcript says "we will expose that endpoint" and the label is a shared device, you know the sentence and you do not know who said it.

## 6. Citation format

`[<key> <locator>] <attribution>`

| Source type | Locator | Attribution |
|---|---|---|
| Recording or transcript | timestamp, `00:41:57` | speaker label, or `ROOM` for a shared device |
| Notes | date, or a heading in your notes | speaker if you noted one, else `ROOM` |
| Document, deck, RFP | page or section heading | document version |
| Email or message | date and sender | sender |
| Intake answer | `intake` plus the date | none |

## 7. Shared-room recordings

A conference-room device appears as one speaker label covering everyone physically in the room, on both sides. On a call held in a room, that label can dominate the recording, and the party behind any given sentence is not recoverable from the label.

Downgrading most of a meeting to `pending` makes the PRD useless, and inferring the party from context is invention. Resolve it with one question instead: ask who was physically in the room and on which side, and bring the attendee list to the question so it comes with a candidate list rather than as an open prompt. That single answer is the attribution key for the whole engagement.

Without an answer, the content still lands as `confirmed-unattributed` and the Owner cells go to `(TBD - <owner>)`.

## 8. Names

Automatic transcription mangles proper nouns, including the client's own name, and the Document Header asks for real names. A mangled name is a visible defect in a client-facing document, and correcting it by guessing is the same invention the rest of this skill forbids.

**Transcript body text is not a source for a person's name.** Precedence, highest first:

1. a written source the client controls: the RFP, an email signature, the contact list they sent you
2. the meeting invitee list
3. the recording's **speaker label**, which is metadata rather than transcription output
4. `(TBD)`

Never transliterate a mangled name into the header.

## 9. The ledger never ships

Locators, speaker labels, and source keys do not appear in the client-facing document, in any section, in any cell. This is also the control that keeps a participant identifier out of the PRD: a shared device label or a partially masked phone number is the natural thing to paste into a Citation cell, and because citations never ship, it cannot reach the document.

Before you fill the template, check that the ledger is complete, that every section has at least the rows it needs, and that the answers you gathered by intake are all marked `author-supplied`. Fill from the ledger, not from the sources.
