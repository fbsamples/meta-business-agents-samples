# API contract

Rules that apply to every Meta Business Agent Platform call in this kit. Other references assume
these and do not restate them.

**This file does not reproduce request and response schemas.** They are published and maintained,
and a copy here would drift. Read the OpenAPI spec for an endpoint before calling it.

## Where the documentation is

Everything lives under `https://developers.facebook.com/documentation/meta-business-agent/`.

Guides, read once:

| Page | Why |
|---|---|
| `overview` | Eligibility rules, requirements, pricing |
| `get-started` | The full setup sequence, and the two traps below |
| `capabilities` | What the agent can do and where each is configured |
| `troubleshooting` | Error envelope, status codes, connector failure taxonomy |

OpenAPI specs, read per endpoint before first use in a session:

| File | Covers |
|---|---|
| `openapi/eligibility.yaml` | `agent_eligibility` |
| `openapi/onboarding.yaml` | `agent_onboarding` |
| `openapi/settings.yaml` | `agent_config/settings` |
| `openapi/allowlist.yaml` | `agent_config/allowlist` |
| `openapi/skills.yaml` | `agent_config/skills` |
| `openapi/knowledge_business_info.yaml` | `agent_config/business_info` |
| `openapi/knowledge_fa_qs.yaml` | `agent_config/faq` |
| `openapi/knowledge_files.yaml` | `agent_config/files` |
| `openapi/knowledge_websites.yaml` | `agent_config/websites` |
| `openapi/connectors.yaml` | `agent_connectors` |
| `openapi/connector_tools.yaml` | `agent_connectors/{id}/tools` |
| `openapi/agent_test.yaml` | `agent_test` |
| `openapi/agent_eval.yaml` | `agent-eval` |
| `openapi/agent_event.yaml` | `agent_event` |
| `openapi/config_versions.yaml` | `agent_config/versions` |
| `openapi/delete_agent.yaml` | Delete agent |

**Read the spec before calling an endpoint you have not called in this session.** Do not reconstruct
a request body from memory or from another endpoint's shape.

If the environment cannot reach the documentation, ask the operator to paste the relevant spec
rather than guessing at a payload.

## Credentials and `.env`

All secrets — the platform access token and connector credentials — go in `.env`.
The CLI reads this file; the assistant does not. Connector credentials may be referenced as
`${VAR_NAME}` only in supported `auth_config` credential fields. Each reference must occupy
that entire value: do not embed it in a URL, description, skill body or FAQ. `MBA_*` values
are reserved for the platform client and cannot be interpolated into configuration content.

Each skill's declared local content must be a regular Markdown/text file, or a YAML FAQ list.
Keep these files inside the configuration directory without symlinks. Do not use credential or
state files as content. Add secret references only in the authentication fields described above.

`.env.example` documents every key the kit uses. Copy it to `.env` and fill in the values:

```
MBA_TOKEN=          # system user token
MBA_ENTITY_ID=      # WhatsApp Business phone number ID
ORDERS_API_KEY=     # connector credential (example)
```

**Never paste a secret into the conversation.** If a secret is pasted anyway, do not use it and do
not repeat it. Tell the operator to treat it as exposed and rotate it immediately — it is now in a
transcript that may be saved or shared.

**Never place a secret where it can be read back** from a process listing, shell history, or log.
Never log full request headers, which carry the token.

`GET /debug_token` reports what a token can actually do without revealing its value. Its
`granular_scopes[].target_ids` lists which WhatsApp Business accounts granted each permission,
which resolves most `403`s immediately.

## Two traps, both documented, both caught constantly

Read the detail in `get-started`. Named here because they account for most early failures:

- **Use the documented version for each endpoint.** Meta Business Agent Platform endpoints
  use `X-API-Version: 2.0.0`. Cloud API endpoints differ: Thread Control takes `1.0.0`.
  Omitting a version can select older field names; read the endpoint reference instead of
  applying one header to every API.
- **`entity_id` is the WhatsApp Business phone number ID**, not the WhatsApp Business account ID
  and not the business portfolio ID. The wrong one produces a `404` that reads like the agent does
  not exist.

## Thread control and the standby webhook

While MBA holds thread control, consumer messages arrive on the **`standby` webhook field**, not
`messages`. The `messages` field carries messages when your app holds control. The
`messaging_handovers` field notifies when control changes hands.

An app that only subscribes `messages` will see nothing while MBA is responding — which looks like
a broken agent but is correct behaviour. See `references/thread-control.md` for webhook setup.

## Skills size limits

Each skill body is capped at 20,000 characters. Exceeding it returns a `400`. See
`references/agent-skills.md` for per-field limits and what to move out of skills to stay within
them.

## An empty response is never a pass

If an `mba` command or curl call returns nothing — no JSON, no error — something went wrong
silently. The most common cause is a missing or misset variable. Run `mba doctor` to check setup,
or verify variables are set before assuming a call succeeded.

Most successful calls return a JSON response body — check for it explicitly. The exception is
DELETE, which returns 204 with no body on success.

## Errors

The envelope, status codes and connector failure taxonomy are in `troubleshooting`. Two operational
rules on top of it:

- **Record `fbtrace_id` on every failure.** It is also in the `X-FB-Request-ID` response header on
  every response. It is what support needs to locate a specific call, and the single most useful
  thing to include in an escalation.
- **Never retry a failed write automatically.** A failure mid-sequence can leave state the next call
  depends on. Surface it and let the operator decide.

## The write pattern

Every mutating operation follows four steps, because configuration changes affect a live agent and
there is no sandbox.

1. **Read** current state with the matching `GET`.
2. **Diff and confirm.** Show what will change and get an explicit yes. Never write on inference.
3. **Write.**
4. **Verify by re-reading.** A `2xx` is not confirmation.

Step 4 is the one people skip, and it is the one that catches real failures. A write can succeed
and the object can still be absent from later reads. Configuration changes also propagate with
variable delay — verify by polling rather than checking once.

## Bulk operations

Real agents carry hundreds of knowledge entries, so most write sessions are batches:

- Confirm the whole batch once, then execute. Do not prompt per item.
- Stop at the first failure. Report what was written and what was not.
- If a response was lost, read the live state and create a fresh reviewed plan. A verified no-op
  apply can reconcile an interrupted attempt; re-run the complete evaluation before enabling.
  Do not retry a write merely because its response was absent.
- Never partially write a single logical object.
- Re-read at the end and reconcile counts against what was sent.
