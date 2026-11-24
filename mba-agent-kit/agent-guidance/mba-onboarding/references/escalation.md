# Escalation

Some failures cannot be fixed from outside the platform. Recognising one early is worth more than
any workaround, because the alternative is days spent debugging configuration that was never the
problem.

This file is about knowing when to stop and what to send.

## Check before escalating

1. **Preflight:** verify terms, the documented billing requirements, eligibility, token
   permissions and whether the agent is enabled.
2. **Target:** confirm the business phone number ID and current configuration.
3. **Stored status:** re-read the resource, including `active`, `pending_review`, or `blocked`
   skill status. If the API returns `contentRejected`, revise content to comply with the
   published policy. Do not work around filtering or assume it caused a missing resource.
4. **Backend:** use `mba logs <connector>` and compare the request with the backend contract.
5. **Processing:** confirm that uploaded knowledge is ready before using it.

If the documented checks do not explain the failure, report the reproduction and responses
without asserting which internal service caused it. A slow connector, missing reply, or failed
write can have several causes; do not label it platform-side without evidence.

## What to send

An escalation that gets resolved quickly looks like this. An escalation missing the first two items
gets a request for them and loses a day.

- **`fbtrace_id`** from the failing response, or the `X-FB-Request-ID` header, which is present on
  every response including empty ones. This is how the specific call gets found.
- **A conversation ID** if the failure happened in a conversation.
- **The `entity_id`.**
- **The exact request**, with the token and any credentials removed.
- **The exact response**, including the full error body.
- **When it started**, and whether it ever worked.
- **What you already checked** from the list above. Saying "preflight passes, agent is enabled, write
  reads back correctly" removes the first round of questions.
- **How reproducible it is.** Every time, intermittently, or once.

Never include an access token, an API key, or a client's customer data. Redact before sending, and
redact again before pasting anything into a shared channel.

## Where to send it

Follow the public [Meta Business Agent support guide](https://developers.facebook.com/documentation/meta-business-agent/support)
for the appropriate support route. Use the offered Direct Support or community option, or
contact a Meta representative where the public guide calls for one. Do not share credentials
or customer data in a public issue or forum.

Record the support reference privately so follow-up work can refer to the same report.

## Reproduction checklist

- For delivery failures, include audience, eligibility and documented billing checks.
- For tool failures, include the stored tool definition, redacted direct-call result and
  conversation symptom. Do not assume a missing tool call proves a routing defect.
- For latency, include redacted connector timing and corresponding backend timing so support
  can investigate without guessing where the delay occurred.

## While you wait

**Ship a workaround if one exists.** Plain text instead of an interactive component. A knowledge
entry instead of a connector call. A handoff instead of a capability. Keeping the engagement moving
is usually worth more to the client than the elegant version, and the workaround can be reverted.

**Tell the client what is happening**, in their terms: what does not work, what you are doing about
it, and whether it blocks their launch date. Silence during an escalation is what damages trust, not
the fault itself.

**Write down what you find.** The symptom, what you tried, and how it resolved. The next person
who hits the same thing will find a known symptom with a known answer, and that costs minutes
instead of days.
