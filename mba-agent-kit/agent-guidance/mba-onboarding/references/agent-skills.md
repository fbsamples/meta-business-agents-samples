# Agent skills

How the agent behaves, as distinct from what it knows. Two endpoints:

| | Endpoint | Controls |
|---|---|---|
| Skills | `agent_config/skills` | Tone, priorities, response patterns, business rules, guardrails |
| UI skills | `agent-ui-skills` | When and how the agent sends interactive components |

Note that UI skills and UI components are documented as two pages against the same endpoint, and the
path parameter is still named `{instruction_id}` — a leftover from before instructions were renamed
to skills. Do not go looking for a second endpoint.

## Skills versus knowledge

The line is not always obvious and getting it wrong produces an agent that knows things but behaves
badly, or behaves well and knows nothing.

- **Knowledge** is what is true. Opening hours, the returns policy, the answer to a question.
- **A skill** is how to act. When to ask a clarifying question, what never to promise, which order to
  do things in, what tone to use, when to hand off.

"We are open until 9pm" is knowledge. "Never quote a delivery date without checking the order first"
is a skill.

## Skills are documents, not form fields

This is easy to underestimate. A production agent's skills are long, structured
instruction documents — a full orchestration spec with data-sourcing rules, state handling, guardrails
and error behaviour. A real commerce agent typically runs three or four of them, layered.

Treat them as source code:

- **Keep them in version control on your side**, as the master copy. The API is where you deploy
  them, not where you author them.
- **Diff before writing.** Read the live skill, diff against your copy, show the change.
- **Layer them rather than writing each client from scratch.** One skill carrying the rules that are
  true for every client you onboard, one per vertical, and one per client for what is genuinely
  specific. Most of any given client's configuration is not specific to them, and maintaining that
  by copy-paste means fixes never propagate.

That layering is the difference between your second client taking as long as your first and taking a
fraction of it.

## Skill size limits

Each skill has documented per-field size limits:

| Field | Max | Notes |
|---|---|---|
| `title` | 64 chars | Lowercase letters, numbers and hyphens only. Must not start or end with a hyphen. |
| `description` | 1,024 chars | The agent reads this to decide which skills apply. Be specific about the trigger. |
| `skill` body | 20,000 chars | The actual instructions. Exceeding this returns a `400`. |

The body limit is a per-write constraint checked at the API. Keep each skill focused — if a single
skill body is approaching 20,000 characters, it almost certainly contains multiple concerns that
should be split into separate skills.

**What to move out of skills to stay within limits:**
- Static Q&A belongs in FAQs, not skills. FAQs are retrieved by semantic search at inference time
  and do not count against skill limits.
- Parameter mechanics and output formatting for a connector belong in connector/tool descriptions,
  not in the skill that calls them.

This means the highest-leverage restructuring move is relocating static Q&A from skills into FAQs,
freeing skill space for actual behavioural rules.

## Skill status and content rejection

Read the skill's documented `status` after writing it. A skill can be `active`,
`pending_review`, or `blocked`; presence alone does not mean the agent will use it.
The API may also reject a write with `contentRejected`.

If content is blocked or rejected, review it against the published Business AI policy and
revise it to comply. Do not identify trigger words or reword prohibited content merely to
avoid a filter. Do not assume filtering caused a missing skill: check the status and error
response, confirm the target and size limits, and use the public support route if the
result is unexplained.

After an accepted revision, re-read the stored skill and test the intended behavior before
launching. Report any pending review or blocked status to the operator.

## UI skills

These direct the agent to send interactive components rather than plain text. They fail differently
from ordinary skills: the agent builds the component correctly and the customer sees nothing.

Two causes worth knowing:

- **Broken or unreachable media.** A component referencing an image the platform cannot fetch fails
  to render, silently. Use stable, production URLs; development or staging CDNs are a common cause.
- **Invented parameters.** Where a component has optional fields the configuration did not set, the
  agent may fill them in itself, and a fabricated value can break rendering. Constrain the skill to
  the fields you actually configured, and say explicitly which ones must not be generated.

Component limits — button counts, character limits, row counts — are real and a flow that exceeds
one is not buildable. Check them while designing the flow rather than discovering it at test.

## Verify

1. Read back by ID. Presence, not a `2xx`, is the proof.
2. Compare the stored text against your copy. Truncation and escaping problems show up here.
3. Exercise the behaviour through the test endpoint. A skill that exists is not a skill that works —
   the agent has to actually apply it.

Step 3 is where you find out that two skills contradict each other, which is the normal failure once
there are more than two.

## Testing skills against the PRD

The PRD is the test specification. Do not write generic test cases — generate them directly from
the PRD:

- **Section 4 flows → happy path tests.** One test per JTBD. The flow steps are the expected
  conversation. Run the opening message and check the response matches step 2 of the flow.
- **Section 4 error paths → edge case tests.** "Order not found", "API unavailable", "user gives
  invalid input" — every error branch in the flow is a test.
- **Section 4 escalation scenarios → escalation tests.** Any flow that ends in handoff should be
  tested: does the agent say the right thing, or does it try to act?
- **Section 5 requirements → one test per behaviour requirement.** "Agent never quotes a price"
  is a requirement. Test it by asking for a price.

**Run four tests per skill:**

| Test | What it proves |
|---|---|
| Happy path | The skill fires and produces the right response |
| Non-trigger | A similar but different scenario does NOT trigger this skill unexpectedly |
| Escalation | The agent hands off correctly and does not attempt what it cannot do |
| Conflict check | If you have multiple skills, an ambiguous message routes to the right one only |

These change per vertical and per client — the PRD is the source, not this list. A WISMO agent's
conflict check is "I returned my shoes, where is my refund?" — touching both return and order
status. A booking agent's conflict check is different.

**Run the full set after every skill change.** Changing one skill can break another. The PRD-derived
tests are the regression suite — run them all, not just the one relevant to the change.

## When it goes wrong

| Symptom | Likely cause |
|---|---|
| Skill missing after a successful write | Re-read the documented status and error response; verify the target and use public support if unexplained. |
| Agent ignores a rule you wrote | Another skill contradicts it, or the rule is ambiguous. Test in isolation. |
| Component never renders | Unreachable media, or a fabricated parameter. |
| Agent invents values | The skill did not constrain the field. Name what must not be generated. |
| Behaviour changed without a write | A shared or inherited skill changed upstream. Read everything back and diff. |
