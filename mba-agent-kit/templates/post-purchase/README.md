# Post-purchase support template

For stores whose customers come back after buying: "where is my order", returns and exchanges,
refund status, and problems that need a person. Adapted from Meta's
[post-purchase support agent guide](https://developers.facebook.com/documentation/meta-business-agent/usage-guides/post-purchase-support-agent).

## What you get

| File | Purpose |
|---|---|
| `agent.yaml` | Settings, business info, four skills, FAQs, help-center crawl, allowlist, and the `store_orders_api` connector with four tools |
| `skills/*.md` | The skill bodies: order status, returns and exchanges, refund status, problems and handoff |
| `faqs.yaml` | Starter FAQs to replace with your real answers |
| `evals/*.yaml` | Nine scenarios written against the mock data (orders 1001, 1002, 1003) |
| `mock-backend/server.py` | A stub of the connector contract, for when you don't have your own order API yet |

## The connector contract

Your order system (or an adapter in front of it) needs four endpoints. Each receives the
customer's WhatsApp number from the platform, never from the model, to scope results to them.

| Tool | Request | Returns |
|---|---|---|
| `list_orders` | `GET /orders?customer_phone=` | recent orders: number, date, status |
| `get_order` | `GET /orders/{order_number}?customer_phone=` | items (with `returnable`, `return_by`), status, carrier, tracking, estimated delivery |
| `create_return` | `POST /orders/{order_number}/returns` `{item_ids, reason, customer_phone}` | return ID, label URL, instructions |
| `get_refund_status` | `GET /orders/{order_number}/refunds?customer_phone=` | refunds: amount, status, date |

If your API differs, change the tool `request_definition`s in `agent.yaml`, not the skills.

## No order API yet? Use the mock backend through a Cloudflare tunnel

Connectors need a public HTTPS URL. Run the mock locally and expose it with a Cloudflare quick
tunnel; don't use other hosting for the mock.

1. Put the same key in `.env` as `ORDERS_API_KEY` and start the mock with it:
   ```bash
   MOCK_API_KEY=<value of ORDERS_API_KEY> python3 templates/post-purchase/mock-backend/server.py
   ```
2. In a second terminal ([install cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) if needed, e.g. `brew install cloudflared`):
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```
   It prints a URL like `https://random-words-here.trycloudflare.com`.
3. Set the connector's `base_url` in `agent.yaml` to that URL plus `/api/v1`, e.g.
   `https://random-words-here.trycloudflare.com/api/v1`.
4. Keep both processes running while you test. The tunnel URL changes every time cloudflared
   restarts: update `base_url`, then `mba plan` and `mba apply` again.

When your real API is ready, replace `base_url` (and the tool definitions if needed) and stop both.

## Steps

1. `mba init --template post-purchase`, then replace every `TODO` in `agent.yaml` and `faqs.yaml`.
2. Set `base_url`: your own API, or the tunnel URL from the section above.
3. `mba plan`, review, `mba apply --plan-id …`.
4. `mba run-tool store_orders_api get_order --input '{"order_number": "1001"}'` to check the connector.
5. `mba eval` until every scenario passes; read the transcripts against each `success_criteria`.
6. On your real API, rewrite the evals around real test orders.
7. Go live gradually: allowlisted numbers first, then `ai_audience: EVERYONE`.

## Business events

When something happens in your system, such as an order shipping or a delivery failing, send it to
the agent so it can act in that customer's conversation. Events are processed asynchronously; check
one with `mba event get --id …`. Whether the agent messages first depends on your setup and the
WhatsApp messaging window, so try it on an allowlisted number.

```bash
mba event send --to +15555550100 --type order_shipped \
  --payload '{"order_number": "1001", "carrier": "UPS", "tracking_number": "1Z999AA10123456784"}' --yes
```
