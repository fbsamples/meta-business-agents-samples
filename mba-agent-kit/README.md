# mba-agent-kit

Set up a [Meta Business Agent](https://developers.facebook.com/documentation/meta-business-agent/overview)
on WhatsApp — from first discovery conversation to a configured, tested, live agent.

Open this directory in your AI coding assistant and describe what you want to build. It guides you
through the whole journey — requirements, configuration, testing and launch — running the `mba` CLI
on your behalf at each step. You can also run `mba` commands directly from the terminal.

> **Prototype sample.** This repository is not evidence of validation against a live business
> number. Verify behavior and supported API contracts before using it with customer traffic.

## Quick start

```bash
# Install the CLI
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Only source/editable installation is supported. Keep this directory in place: the CLI loads
its schema, API specifications and templates from the checkout. Installing a standalone wheel
or source archive is not supported.

Open `.env` in any text editor and fill in your credentials:

```
MBA_TOKEN=your_system_user_access_token
MBA_ENTITY_ID=your_whatsapp_phone_number_id
```

On macOS you can open it with `open -e .env` (TextEdit) or `nano .env` in the terminal.
See [Getting API credentials](https://developers.facebook.com/documentation/meta-business-agent/get-api-key)
for how to generate a system user access token and find your phone number ID.

Then open your AI coding assistant in this directory and ask:

> "Read AGENTS.md and agent-guidance/mba-start/SKILL.md, then help me set up a Meta Business Agent."

The assistant will ask about the business, credentials and existing integrations before making
changes. Guidance in `agent-guidance/` is not automatically installed as slash commands.

For Claude Code, you can optionally install the bundled skills in this project:

```bash
mkdir -p .claude/skills
for name in mba-start mba-prd-builder mba-onboarding; do
  ln -s "../../agent-guidance/$name" ".claude/skills/$name"
done
```

Do not overwrite an existing skill directory. Restart the assistant after installation; only
then are commands such as `/mba-start` available in harnesses that support this format.

Or work through it yourself:

```bash
mba init --template post-purchase   # start from a working template
mba plan                            # see what would change
mba apply --plan-id <id> --yes      # apply only after explicit review and confirmation
mba eval                            # test before going live
mba enable --yes                    # go live (allowlisted numbers only)
```

## Prerequisites

- A WhatsApp Business phone number eligible for Meta Business Agent, with the Meta Business Agent
  terms accepted in WhatsApp Manager.
- A system user token with `whatsapp_business_messaging` and `whatsapp_business_management` —
  see [how to get one](https://developers.facebook.com/documentation/meta-business-agent/get-api-key).
- Python 3.9+.
- `cloudflared` — only if you use the mock backend for connector testing
  ([install](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)).
- For real customer traffic (not needed for testing): billing set up and webhook fields subscribed,
  per [end-to-end setup](https://developers.facebook.com/documentation/meta-business-agent/get-started).

## What is in it

```
mba/                       # the CLI (doctor, init, pull, plan, apply, eval, enable, …)
templates/post-purchase/   # working template: skills, FAQs, connector contract, mock backend, evals
schema/agent.schema.json   # what agent.yaml accepts (mba schema)
openapi/                   # API specs, X-API-Version 2.0.0
agent-guidance/            # AI assistant skills (tool-agnostic; works with any coding agent)
  mba-start/               # front door — works out where you are and routes you
  mba-prd-builder/         # discovery notes → structured PRD → starter agent.yaml
  mba-onboarding/          # PRD → configured, tested, live agent
AGENTS.md                  # instructions and rules for AI assistants
```

## CLI commands

| Command | Does | Writes? |
|---|---|---|
| `mba doctor` | Checks credentials, eligibility, onboarding, go-live gate | no |
| `mba init --template NAME` | Copies a use-case template into this folder | local files |
| `mba pull` | Exports the live agent to `agent.yaml` | local file |
| `mba plan [--prune]` | Diff of `agent.yaml` vs. live | no |
| `mba apply --plan-id ID --yes` | Applies a target-bound reviewed plan; refuses if stale | **yes** |
| `mba onboard --yes` | Creates the agent on the number | **yes** |
| `mba test "msg"` | One test message (not billed) | no |
| `mba eval [-v] [--only …]` | Runs `evals/`, records result for the go-live gate | no |
| `mba eval-remote cases\|run\|status` | Meta's server-side evals | run: **yes** |
| `mba run-tool CONN TOOL --input JSON` | Calls one connector tool directly | calls your API |
| `mba logs CONN` | Connector call logs and success rate | no |
| `mba versions` / `mba rollback ID --yes` | Config history / serve an earlier version | rollback: **yes** |
| `mba enable --yes` / `mba disable --yes` | Turn the agent on (gated) / off | **yes** |
| `mba event send … --yes` / `get` | Send a business event (e.g. order shipped) | **yes** |
| `mba schema` | Print the JSON Schema for `agent.yaml` | no |

Every command takes `--json` for machine-readable output.

## Credentials

All secrets go in `.env`. Connector secrets are referenced as `${VAR_NAME}` only in supported
`auth_config` credential fields; literal secret values and interpolation elsewhere are rejected.
API-key values and OAuth client secrets must contain at least eight characters. OAuth client IDs
may be literal values or environment references.
`MBA_TOKEN` and `MBA_ENTITY_ID` are reserved for the platform client and cannot be interpolated.
`.env` and local approval/evaluation state in `.mba/` are ignored by source control. Your AI
assistant never reads `.env` or the local approval key. YAML aliases, including merge aliases,
are not supported in `agent.yaml`, FAQ files or evaluation scenarios; write distinct values
instead of referencing shared mappings.

`mba pull` omits connector authentication. Add credential references yourself before planning
connector creation or updates. To rotate an existing connector credential, disable the agent,
then use matching `--rotate-credentials NAME` options on both `plan` and `apply`.

Never paste a token into a conversation. If one is pasted by accident, treat it as exposed and
rotate it immediately.

## Safe configuration and launch

The gate is bound to the selected business number, API origin, current live configuration, and
complete canonical evaluation suite beside `agent.yaml`. Changing the target, suite or
configuration invalidates approval. Partial applies leave the gate closed.

Disable an enabled agent before changing its behavior or credentials. For supported unversioned
targets, configure while disabled, run the complete `mba eval`, then enable behind `ALLOWLISTED_ONLY`.
The gate also fingerprints live knowledge files and non-secret connector identity-injection settings.

**Versioned-target limitation:** the public versioning API reports the default active version,
but does not provide a supported rule-listing operation that proves every customer receives that
configuration. This prototype therefore blocks gated evaluation, enabling and live audience widening
for versioned targets rather than using an undocumented endpoint or assuming experiments are absent.
Version listing and explicit rollback remain available. There is no flag to bypass this limitation.

Widening exposure requires
explicit `--widen-audience` confirmation in addition to `--yes`; it does not bypass evaluation.
For example, after reviewing the audience-only change:

```bash
mba plan
mba apply --plan-id <id> --yes --widen-audience
```

Enabling an `EVERYONE` audience also requires `mba enable --yes --widen-audience`.
`mba run-tool` requires `--yes` for any tool that is not an HTTP GET. Evaluations can call your
backend: use synthetic records and sandbox credentials so tests cannot modify real orders.

## Contributor checks

From this directory, install development dependencies and run the offline checks:

```bash
pip install -e '.[dev]'
python3 -m unittest discover -s tests -v
```

CI additionally validates every bundled specification with `openapi-spec-validator`.

These checks do not contact the live Meta Business Agent API. Passing them is not evidence that
the prototype has been exercised against a real business number.

## How it relates to the API documentation

This kit encodes **sequence, judgment and failure modes** — the order things must happen in, the
traps that are not obvious from a reference page, and what to do when something breaks.

It does not reproduce request and response schemas. Those are in `openapi/` and at
`developers.facebook.com/documentation/meta-business-agent/reference/`. Where this kit and the
published documentation disagree, the documentation is right.
