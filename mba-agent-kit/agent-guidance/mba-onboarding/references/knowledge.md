# Knowledge

What the agent knows. Four sources, each a separate endpoint, all under `agent_config/`.

| Source | Endpoint | Use it for |
|---|---|---|
| Business info | `business_info` | Hours, locations, contact details, policies. One structured object. |
| FAQs | `faq` | Question and answer pairs. The workhorse. |
| Files | `files` | Unstructured documents. Ingested asynchronously. |
| Websites | `websites` | URLs the agent crawls and re-reads periodically. |

The public onboarding API accepts a `catalog_id` where catalog support is available. This kit
does not provide an `agent_config/catalog` endpoint; follow the published catalog and onboarding
guidance instead of inventing a catalog operation.

## FAQs must come from the client — never invent them

**Before writing or loading a single FAQ, ask the client for their source material.**

FAQ content that goes into the agent will be presented to real customers as fact. If the return
window is wrong, the agent will tell customers the wrong thing. If the support phone number is
made up, customers will call a number that doesn't exist.

Ask for any of the following — whichever the client already has:
- An existing FAQ or help center page
- A returns or exchange policy document
- Customer service scripts or call center guidelines
- A product information sheet

If the client has nothing written down yet, tell them: "I need the actual policy content from you
before I can load FAQs. I can tell you which categories to cover — returns, delivery, exchanges,
sizing, payment — but the answers must come from you."

**The skill extracts and structures what the client provides. It does not invent.**

The only exception is a test or demo where invented content is used to validate mechanics before
the real engagement. In that case, document clearly that the content is placeholder and must be
replaced before any real customer sees it.

## How FAQs are retrieved

FAQ answers are retrieved by **semantic search**, not exact match. The agent does not find the FAQ
whose question text matches exactly; it finds the FAQ whose meaning is closest to what the customer
asked, and it may paraphrase the answer in its own words.

This has two consequences:

- If you need verbatim wording — legal disclaimers, regulatory text, exact policy language — put it
  in a **skill**, not an FAQ. Skills are injected into the agent's context directly; FAQs are
  retrieved by search and may be paraphrased.
- FAQ answers do not count against per-skill character limits (see `agent-skills.md`).
  When your skills are approaching the budget cap, converting static Q&A content from skills into
  FAQs is the primary way to free capacity without losing the content.

## Choosing between them

People often default to putting everything in FAQs. Some of it belongs elsewhere.

- **A specific question with a specific answer** is an FAQ. Highest precision, and the agent cites
  it directly.
- **A policy document nobody has decomposed** is a file. Lower precision, but it exists today and
  decomposing it into FAQs can wait.
- **Content the client updates on their own site** is a website. It re-reads, so it does not go
  stale, but you control neither the timing nor what gets picked up.
- **Facts about the business itself** are business info, not FAQs. Putting opening hours in an FAQ
  works, but it is the wrong shape and it is harder to keep current.

Where the same fact lives in two places, they will eventually disagree. Pick one home per fact.

## Bulk is the normal case, not the exception

A batch can contain several FAQs, but a larger collection is not automatically better.
The public FAQ reference warns that quality can degrade beyond a few hundred entries.
Keep entries focused and evaluate retrieval before expanding the collection.

- **Confirm the whole batch once**, showing counts and a sample, then execute. Do not prompt per
  item; approval must cover the complete, reviewed change.
- **Stop at the first failure.** Report what was written and what was not, so the retry starts from
  the right place.
- **Reconcile at the end.** Read the collection back and compare the count against what you sent. A
  mismatch means something was rejected silently.
- **Check for duplicates before writing**, not after. Read the existing set first. Re-running an
  upload is a normal thing to do, and doing it twice should not double the knowledge
  base.

Source material usually arrives as a spreadsheet or a document. Show the parsed result before
writing anything — mis-parsed columns are common and much cheaper to catch at that point.

## Files are asynchronous

This is the one that surprises people. Upload returns success; the file is not usable yet.

Ingestion and extraction happen after the upload call returns. Until they finish, the agent cannot
answer from that document, and nothing about the upload response tells you that.

So: **upload, then poll status until processing completes**, and only report success when it has.
"Why is the agent not finding my document" is nearly always a file that uploaded fine and never
finished processing, or one that failed extraction with no notification.

Supported formats and the status values are in the `configure/agent-knowledge-files` reference.
There is no update method — replacing a file means deleting it and uploading again, which means the
agent is briefly without it.

## Websites

You are handing over control of content you do not own. Two consequences worth telling the client:

- Crawl timing is not yours. Content published now is not available now.
- Whatever is on the page is what the agent reads, including things nobody meant it to read. Check
  what is actually at the URL before adding it, not just what the client says is there.

Prefer a specific, stable page over a section root.

## Business info

One structured object, written with `PUT`. Read before writing: it is a whole-object write, so a
partial payload can drop fields that were already set.

## Verify

Knowledge is the easiest configuration to verify properly, so do it:

1. Read the collection back and reconcile counts.
2. For files, confirm processing finished — not just that upload succeeded.
3. Ask the agent something only the new knowledge could answer, using the test endpoint. That is the
   only check that proves the content is reachable rather than merely stored.

Step 3 catches the class of failure where everything looks written and the agent still cannot use
it.

## When it goes wrong

| Symptom | Likely cause |
|---|---|
| Agent does not know something you uploaded | File still processing, or failed extraction. Check status. |
| Count is lower than what you sent | Silent rejection. Read the collection back and diff. |
| Duplicate answers | An upload was run twice without reading existing entries first. |
| Website content missing | Not crawled yet, or the content is not in the fetched HTML. |
| Business info fields disappeared | A `PUT` with a partial object overwrote them. |
| `400` on a batch | `detail` names the field. Fix that item and restart from where it stopped. |
