# Discovery

How to run client discovery so that the PRD mostly writes itself. Following this structure produces a PRD that is legible to any technical stakeholder who reviews it.

Discovery is not a pitch. It is listening, learning, and finding where there is genuine fit. A good
discovery call surfaces things the client has not yet articulated themselves, and it prevents wasted
engineering on both sides.

## The four questions discovery answers

| Type | The question it answers |
|---|---|
| **Technical** | Can we actually build this together? |
| **Business** | Is this worth building? |
| **Process** | How does work actually get done here? |
| **Stakeholder** | Who needs to say yes, and who can say no? |

A complete engagement touches all four, usually across two or three calls. Do not try to cover all
four in one. Depth beats breadth.

## Before the call

**If you can look it up, do not ask it on the call.** Research first:

- What the company does, its scale, recent news
- Their tech stack, from job postings, engineering blog, developer docs, public APIs
- Their messaging presence: already on WhatsApp? What does it look like today?
- What AI tools they already use
- The backgrounds of the people who will be on the call
- Comparable clients you have worked with, and what happened

## The first call

Thirty to sixty minutes. Four questions, held as a conversation rather than an interrogation. Expect
a natural flow of problem determination.

1. **The problem and use case.** If there were one pain point the agent could resolve, what would it
   be? What have you tried or evaluated so far, and what worked or did not?
2. **Current partners and ecosystem.** Walk me through your core stack: commerce platform, CRM, CDP,
   marketing automation. How connected are these today? How are you communicating with customers
   now, and where does AI come in?
3. **Infrastructure and compliance.** What has your legal and security team already defined as
   non-negotiable for AI in customer-facing conversations? Any data residency, privacy, or review
   requirements to factor in early?
4. **End goal.** If we fast-forward twelve months and this worked exactly as you hoped, what would
   be different about your business?

Pacing:

| Length | Discovery types | Split |
|---|---|---|
| 30 min | 1, go deep | 2 intro / 18 discovery / 6 overview / 4 next steps |
| 60 min | 2 to 3 | 5 / 40 / 10 / 5 |
| 90 min | all 4, rare | 5 / 60 with a break at 45 / 15 / 10 |

## How to ask

**Current, then pain, then future, then impact.** That order, with roughly that weighting:

- **Current state**, 60-70% of the time. "Walk me through how that works today." "How does data flow
  from A to B?"
- **Pain and consequences**, 15-20%. "What breaks or slows down?" "What happens when that edge case
  hits?" "What does it cost?"
- **Future state**, 10-15%. "In an ideal world, what does this look like?"
- **Business impact**, 5-10%. "What would solving this mean for that number?"

Every question should be open-ended rather than yes/no, specific rather than general, neutral rather
than leading, built on the previous answer rather than a topic jump, and mapped to something the
product can actually do.

Six principles that matter more than the question list:

1. **Listen more than you talk.** Over 30% of the talking and you are pitching.
2. **Follow the thread.** The best material comes from follow-ups, not the prepared list.
3. **Validate, do not assume.** "You mentioned X, is that because of Y, or something else?"
4. **Name the gap.** "So the gap is between this and that, is that right?"
5. **Capture exact quotes.** "Our agents spend 40% of their time on repeat questions" is worth more
   than "they have efficiency issues," and it is citable in the PRD.
6. **Do not solve on the call.** "Let me take that back" beats improvising an architecture.

## Deep-dive modules

After the first call, pick the modules that apply and run them as technical follow-ups. Each has a
trigger and feeds specific PRD sections.

| Module | Trigger | Feeds |
|---|---|---|
| A · AI and automation maturity | Client has an existing bot or past deployments | §2, §7 |
| B · Technical architecture | Moving to technical scoping, engineers present | §5, §6 |
| C · Commerce | Retail, eCommerce, food delivery, travel | §2, §3, §4 |
| D · Support operations | Goal is support automation or cost reduction | §2, §4, §7 |
| E · Privacy and compliance | Regulated industry, or client raised data concerns | §6, §10 |
| F · Regional | Market-specific practice, payments, regulation | §4, §10 |
| G · Channel strategy | Channel mix and entry points matter | §1, §4 |
| H · Pilot scoping | Client is ready to commit | §3, §7, §8 |
| I · Agent experience design | Moving to build, brand and UX people involved | §1, §4, and the agent's skills and knowledge |
| J · Identity and authentication | Account-specific actions are in scope | §4, §6 |

### A · AI and automation maturity

Walk me through your current bot experience from the customer's side, start to finish. What stack
powers it? What is your containment rate today and what is the target? What are the top three
reasons conversations escalate to a human? What capabilities are missing? Who built and maintains
it? If past AI attempts did not work out, what went wrong?

### B · Technical architecture and integration

What core systems would the agent need to reach: order management, CRM, CDP, ticketing, catalog,
payments, logistics? Do you have a mature knowledge base, and how often does its content change? Are
there long-running workflows the agent would trigger? What APIs can be exposed for real-time access,
and what is typical latency? What is the API architecture and auth model? Can webhooks push events
out? What are the rate limits? Is there a staging or sandbox environment? Who is your WhatsApp
Business Platform provider today? Can you share API documentation or sample payloads? What is your
engineering team's capacity for integration work over the next ninety days?

### C · Commerce

Walk me through the purchase journey and where the friction is. What share of inquiries are order
status? Do you support in-conversation transactions, or must customers leave the chat? Which payment
methods matter most? How does product discovery work in conversations today? What is your cart
abandonment rate and recovery mechanism? How are returns and refunds handled? Do you have seasonal
spikes or flash sales that create volume surges?

### D · Support operations

What is monthly support volume, broken down by channel? What is cost per contact, human versus
automated? Top five inquiry types by volume? What triggers handoff to a human today, and what does
that transition feel like? What is your staffing model, and how do you absorb spikes? What are your
response and resolution SLAs, and are you meeting them? What ticketing or agent desktop platform do
your teams use?

### E · Privacy and compliance

Which data privacy regulations apply? What are your concerns about sharing data with an external AI
provider? What data classification levels exist, and what can and cannot leave your systems? Any
data residency or sovereignty requirements? What security certifications do you require of vendors?
Will a data processing agreement be needed, and standard or custom? What is your review process for
new vendor integrations? What personal data can the agent access or display, and what must be
masked?

### F · Regional

What share of your customers use WhatsApp as their primary channel? Which local payment methods
matter, and would you enable them in-conversation? How are you handling the local privacy regime and
consent management? Which messaging partners do you work with in this market? Language
considerations, including regional variants and language mixing? Any market-specific consumer
protection rules? How are customers identified locally, for example by a national ID number?

### G · Channel strategy

Which messaging channels are active, and what is each used for? Are your WhatsApp notifications
one-way, or can customers reply and continue? What is your opt-in rate for transactional messages?
What entry points drive customers to WhatsApp: ads, website, QR codes, saved contact? Are you
running click-to-WhatsApp ads, and how do they perform? How important is a unified customer view
across channels, and do you have identity resolution today?

### H · Pilot scoping

Which one or two use cases should the pilot cover? What is the scope: channels, segments, markets?
Expected conversation volume? What duration, and what milestones along the way? What quantitative
success criteria decide whether to expand? What qualitative factors also count? What internal
resources are dedicated? What known blockers or dependencies could delay launch?

### I · Agent experience design

What personality and tone should the agent have? Which languages must it support, and are there
mixing scenarios? Are there mandatory brand guidelines for AI communications? What topics must the
agent never discuss? What greeting do you want? What FAQ and knowledge content exists already, how
often does it change, and who owns it? What catalog data is available, in what format, and how
fresh?

### J · Identity and authentication

How is customer identity verified in a messaging thread today? What happens when the phone number
does not match an account? Is there a guest flow, or must everyone authenticate? Is session context
maintained across conversations? Are there different authentication levels for different actions,
for example viewing an order versus initiating a refund? What can be retrieved from a phone number
alone? Any shared-account or multi-device considerations?

## What to capture

After every call, write these five up. They are the input contract for the PRD, and the fact ledger
in `capture.md` is where they live.

1. **Current state map.** Systems and tools in use with vendors and versions, data sources and
   flows, team structure and ownership, volumes and scale.
2. **Pain points, ranked.** For each: what is happening, its impact quantified where possible, the
   root cause, and how they cope today.
3. **Fit assessment.** For each capability under consideration: strong, moderate, weak or no fit;
   the specific evidence; what must be true for it to work; and what could go wrong.
4. **Open questions.** What you still do not know. Be honest, these drive the next call and they
   become §11 of the PRD.
5. **Next steps.** Specific actions, with owners and dates.

## Common mistakes

1. Trying to cover everything in one call.
2. The wrong people on the client side. If you need architecture answers, ask for an engineer.
3. Solutioning mid-call. "We could build X" ends discovery.
4. Asking what you could have looked up.
5. Listing capabilities instead of mapping to stated problems.
6. Not validating assumptions.
7. Forgetting to ask about failures. "What have you tried that did not work?" reveals more than
   "what do you want?"
