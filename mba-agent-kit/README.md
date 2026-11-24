# mba-agent-kit

Set up a [Meta Business Agent](https://developers.facebook.com/documentation/meta-business-agent/overview)
on WhatsApp — from first discovery conversation to a configured, tested, live agent.

Open this directory in your AI coding assistant and describe what you want to build. It guides you
through the whole journey — requirements, configuration, testing and launch — running the `mba` CLI
on your behalf at each step. You can also run `mba` commands directly from the terminal.

> **Prototype.** Not yet run on a live engagement. Treat the guidance as reasoned rather than
> proven, and report where it is wrong.

## Quick start

```bash
# Install the CLI
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[validate]"          # or skip and use `python3 -m mba` where requests and PyYAML exist
cp .env.example .env
```

Open `.env` in any text editor and fill in your credentials:

```
MBA_TOKEN=your_system_user_access_token
MBA_ENTITY_ID=your_whatsapp_phone_number_id
```

On macOS you can open it with `open -e .env` (TextEdit) or `nano .env` in the terminal.
See [Getting API credentials](https://developers.facebook.com/documentation/meta-business-agent/get-api-key)
for how to generate a system user access token and find your phone number ID.

Then open your AI coding assistant in this directory. For example, with Claude Code:

```bash
claude
```

Say something that includes **"Meta Business Agent"** to trigger the right skill. For example:

> "I want to set up a Meta Business Agent."

> "Help me configure a Meta Business Agent for my store."

> "I need to onboard a client to Meta Business Agent."

The assistant will ask a few quick questions (who this is for, whether you have credentials, whether
there is an existing app on the number) before doing anything. If you want to skip the conversation
and invoke the front door directly, type `/mba-start`.

Or work through it yourself:

```bash
mba init --template post-purchase   # start from a working template
mba plan                            # see what would change
mba apply --plan-id <id>            # apply after reviewing
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
.claude/skills/            # Claude skills that drive the CLI conversationally
  mba-start/               # front door — works out where you are and routes you
  mba-prd-builder/         # discovery notes → structured PRD → starter agent.yaml
  mba-onboarding/          # PRD → configured, tested, live agent
AGENTS.md / CLAUDE.md      # instructions and rules for Claude
```

## CLI commands

| Command | Does | Writes? |
|---|---|---|
| `mba doctor` | Checks credentials, eligibility, onboarding, go-live gate | no |
| `mba init --template NAME` | Copies a use-case template into this folder | local files |
| `mba pull` | Exports the live agent to `agent.yaml` | local file |
| `mba plan [--prune]` | Diff of `agent.yaml` vs. live | no |
| `mba apply --plan-id ID` | Applies a reviewed plan; refuses if stale | **yes** |
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

All secrets go in `.env` and are referenced as `${VAR_NAME}` in `agent.yaml`. `.env` is ignored
by source control. Your AI assistant never reads it.

Never paste a token into a conversation. If one is pasted by accident, treat it as exposed and
rotate it immediately.

## How it relates to the API documentation

This kit encodes **sequence, judgment and failure modes** — the order things must happen in, the
traps that are not obvious from a reference page, and what to do when something breaks.

It does not reproduce request and response schemas. Those are in `openapi/` and at
`developers.facebook.com/documentation/meta-business-agent/reference/`. Where this kit and the
published documentation disagree, the documentation is right.
