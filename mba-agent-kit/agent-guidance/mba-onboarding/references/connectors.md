# Connectors

How the agent takes action in external systems rather than only answering questions. This is the
hardest part of an onboarding and the commonest source of delay, because it depends on the
account's engineering rather than on configuration.

Two levels:

- A **connector** describes one external API: its base URL and how to authenticate to it.
- A **tool** is one operation on that connector — look up an order, check stock, book a slot. The
  agent decides when to call it.

Section 6 of the PRD is the input here. If it names endpoints, auth model and the fields that cross
the boundary, this stage is transcription. If it does not, go back to discovery rather than guessing.

## Before the real API is ready — use a mock

The real API is the most common source of delay in a connector build — it often is not ready,
documented, or accessible when you need to start. Do not wait for it.

**Stand up a mock API first.** The post-purchase template ships a ready mock backend:

**Do not source `.env` as shell code or paste its contents.** Ask the operator to load only the
demo key into their environment privately, then start the mock:

```bash
MOCK_API_KEY="$ORDERS_API_KEY" python3 templates/post-purchase/mock-backend/server.py
```

In a separate terminal, expose the synthetic demo with a Cloudflare quick tunnel:

```bash
cloudflared tunnel --url http://localhost:8080
```

The tunnel prints a `https://…trycloudflare.com` URL. Use that URL (plus the path prefix, e.g.
`/api/v1`) as `base_url` in `agent.yaml`.

**If `cloudflared` is not installed:** `brew install cloudflared` on macOS, or see
[Cloudflare's download page](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

Both the mock and the tunnel must keep running during `mba run-tool` and `mba eval`. If cloudflared
restarts, the URL changes — update `base_url` in `agent.yaml`, then `mba plan` → `mba apply`.

For other use cases without a ready mock, build a simple server that exposes the same endpoints
with realistic synthetic responses. The connector definition does not change when you swap to the
real API — only the URL.

## Swapping the mock for the real API

When the real API is ready, swap it in without changing the connector structure:

1. Update `base_url` in `agent.yaml` to the real API's URL.
2. Update `auth_config` / add real credentials to `.env` (e.g. `ORDERS_API_KEY=real_key`).
3. Adjust `request_definition` paths and parameters if the real API shape differs from the mock.
4. Rewrite `evals/` scenarios to use real test records instead of mock order numbers.
5. `mba plan` → review → `mba apply`.
6. `mba run-tool` on each tool with a real test record to verify connectivity.
7. `mba eval` with real data — must pass before `mba enable`.

**Never go live on a mock backend or a `trycloudflare.com` tunnel.** The connector must point at
the real API before the agent is enabled for real customers.

## The order of work

1. Create the connector **without credentials** in `agent.yaml`.
2. Add credentials to `.env` and reference them as `${VAR_NAME}` in `auth_config`.
3. Define the tools.
4. Test each tool directly with `mba run-tool` before the agent is allowed near it.
5. Only then write the skills that tell the agent when to use them.

Step 4 before step 5 matters. A tool that returns the wrong shape produces agent behaviour that
looks like a prompt problem and is not.

## Credentials — never handled in conversation

**All connector secrets go in `.env` and use `${VAR_NAME}` as an entire supported
`auth_config` credential value.** Do not interpolate them into URLs, descriptions or skills.
The assistant never reads `.env`. `MBA_*` values cannot be used as connector credentials.

`mba pull` omits authentication. Add credential references before planning an authenticated
connector create/update. To rotate an existing credential, disable the agent, update its `.env`
value, then run:

```bash
mba plan --rotate-credentials store_orders_api
mba apply --plan-id <reviewed-id> --rotate-credentials store_orders_api --yes
```

The rotation flags must match the reviewed plan. Remote masked credentials are never copied
into configuration or sent back as replacement secrets.

If a secret is pasted into the conversation: do not use it, do not repeat it, and tell the operator
to treat it as exposed and rotate it immediately.

**The supported auth modes are `OAUTH2_CLIENT_CREDENTIALS`, `API_KEY`, and `NONE`.**
Use the mode documented for the backend; do not substitute `OAUTH2`, `BASIC` or `CUSTOM`
for unsupported enum values. Client credentials and API-key secrets use `.env` references.
The public connector documentation describes connection statuses such as `PENDING_OAUTH`;
a status is not itself an authentication-mode enum.

Credentials are rotated using the same upsert endpoints used to set them — tell the account owner
this up front so rotation does not require a re-onboarding.

## Tools

Each tool needs a name and description the **agent** will read, not just a human. The description
is how the agent decides whether this is the right tool for the customer's request.

**Tool name style.** Use `snake_case` with a clear action verb: `get_order`, `create_return`,
`check_refund_status`. Avoid generic names like `action1`.

**Descriptions must include 3–5 example user phrases.** "Use this to look up an order" will not
fire reliably. "Use this when a customer asks things like: 'where is my order', 'what happened to
my package', 'track my delivery'" will. The agent matches the tool description to the customer's
phrasing at inference time — example phrases are the highest-leverage words in a connector
definition.

**Customer identity binding — never let the model supply it.** On the parameter your API uses to
scope results to a specific customer, always use the `WHATSAPP_PHONE_NUMBER` macro:

```yaml
customer_phone:
  type: string
  description: The customer's WhatsApp phone number.
  binding:
    kind: macro
    macro: WHATSAPP_PHONE_NUMBER
```

This automatically binds the customer's real WhatsApp phone number (the one they are messaging
from) to the API call. The agent never asks for it and cannot be given someone else's. Without this
binding, a customer could supply any phone number and retrieve another person's data.

**For writes (create, cancel, change): the customer must confirm the exact change before the tool
fires.** State this in the tool description: "Only call after the customer has confirmed which items
and the reason." The agent reads the description to decide how to behave.

**`transformation_spec` — trim the response.** If the API returns more data than the agent needs,
define a `transformation_spec` on the tool to trim the response before it reaches the agent. A
large nested payload makes the agent slower and more likely to misread it.

## Test each tool before the agent sees it

```bash
mba run-tool <connector_name> <tool_name> --input '{"order_number": "1001"}'
```

This executes one tool directly with no conversation involved. Use it on every tool as you define
it. A non-GET tool also requires `--yes` after explicit confirmation; use synthetic test records
because a direct tool call can perform writes on the connected backend.

This separates three failures that otherwise look identical from the outside:
- the API is broken or unreachable
- the tool definition is wrong (wrong path, wrong parameters)
- the agent is choosing the wrong tool or calling it with bad arguments

Without direct execution, all three present as "the agent gave a wrong answer" and you will debug
the wrong layer.

## Diagnosing live failures

```bash
mba logs <connector_name>
```

The runtime call log, and the first place to look when a live conversation goes wrong. Each entry
carries a `failure_code_name` and an error message.

The full taxonomy is in the published `troubleshooting` page. What matters operationally is **who
owns the fix**:

| Owner | Failure codes | Meaning |
|---|---|---|
| **Credentials** | `UNAUTHORIZED`, `AUTHORIZATION_CHECK_FAILED` | Rotate, or the key lacks a scope. Update `.env`. |
| **The external API** | `TRANSPORT_ERROR`, `API_RATE_LIMIT_EXCEEDED`, `EXTERNAL_API_ERROR` | Not your configuration. The API owner fixes it. |
| **Your configuration** | `NOT_FOUND`, `INVALID_REQUEST_USER` | Wrong path, wrong parameters, or a binding that resolves to the wrong type. |

`connection_status` on the connector itself reports whether it can make calls at all — `ACTIVE`,
`PENDING_OAUTH`, `EXPIRED` or `ERROR`. Check it before reading logs; a connector stuck in
`PENDING_OAUTH` has never made a call.

## MCP-backed connectors

Where the API exposes tools through an MCP server, the connector can read its tool list from the
server. Re-read after any change on the server side:

The `mba` CLI does not provide a refresh command for MCP tools. Read the corresponding public
API specification and use the documented refresh operation, with explicit confirmation for
any mutation.

A tool the agent believes exists and the server no longer exposes fails at runtime in a live
conversation.

## When it goes wrong

| Symptom | Likely cause |
|---|---|
| Connector stuck `PENDING_OAUTH` | Authorization was never completed. Not a configuration problem. |
| Tool returns empty data | Output shape mismatch. Run it directly and compare against the API. |
| Agent never calls a tool | The description does not match how customers phrase the request. |
| Agent calls the wrong tool | Two descriptions overlap. Make the boundary explicit in both. |
| Works directly, fails in conversation | Argument binding. The agent is passing something different from your test. |
| Worked yesterday, fails today | Credential expiry or the API changed. Check `mba logs` first. |
| Slow responses | Each tool call costs a round trip. Reduce the number needed per turn. |
| Tool accepted but never executes | Connector may not have finished initialisation. Wait a minute, then retry `mba run-tool`. |
| Tunnel URL changed | cloudflared restarted. Update `base_url` in `agent.yaml`, plan and apply. |
