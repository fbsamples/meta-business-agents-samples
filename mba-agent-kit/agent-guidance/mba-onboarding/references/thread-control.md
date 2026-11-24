# Thread control

For BSPs and third-party apps that need to coexist with Meta Business Agent on the same
WhatsApp Business phone number.

When MBA is enabled on a number, it becomes the **primary responder** — it handles all new
conversations automatically. Your app moves to a **standby** role. Understanding how control passes
between the two is what makes the integration work.

This guide covers two scenarios. Both require the same webhook setup. The second requires an
additional configuration step.

---

## Step 1 — Subscribe the right webhook fields (required for both scenarios)

Your app needs two fields beyond `messages` to stay in sync with MBA conversations:

| Field | What it delivers |
|---|---|
| `messages` | Messages your app receives when **it** holds thread control |
| `standby` | Messages the user sends while **MBA** holds thread control — your app can read but not respond |
| `messaging_handovers` | Fired whenever thread control changes hands |

**How to subscribe:**

1. Go to [developers.facebook.com/apps](https://developers.facebook.com/apps/) → open your app
2. Left nav → **WhatsApp → Configuration**
3. In **Webhook fields**, subscribe to:
   - `messages` (likely already subscribed)
   - `standby`
   - `messaging_handovers`

Without `standby`, your app is blind to conversations while MBA is responding. Without
`messaging_handovers`, your app does not know when control changes and cannot react correctly.

---

## Scenario A — Read conversations while MBA holds control (standby mode)

Your app monitors conversations and can step in by sending a message. Sending any message
automatically transfers control to your app.

**How it works:**

1. User messages the business → MBA responds → messages arrive on your app's `standby` webhook
2. You decide to intervene → send a message from your app → control transfers to you automatically
3. You are done → release control back to MBA:

```bash
curl -X POST "https://api.facebook.com/business/whatsapp/phone_numbers/$ENTITY_ID/thread_control" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-API-Version: 1.0.0" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "action": "release",
    "to": "<CONSUMER_PHONE_NUMBER>"
  }'
```

After a successful `release`, MBA resumes as the primary responder. The user's messages go back to
the `standby` field on your app.

**`to`** is the consumer's phone number or WhatsApp ID — the person whose conversation you are
releasing. Replace `<CONSUMER_PHONE_NUMBER>` with the value from the incoming webhook.

Reference: [Thread Control (Cloud API)](https://developers.facebook.com/documentation/meta-business-agent/reference/operate/thread-control-cloud-api)

---

## Scenario B — Full escalation partner flow (take and release)

Your app is configured as the **escalation partner** on the phone number. This lets it take control
proactively — before sending any message — so a human agent can read the conversation first.

**Additional setup required:**

Confirm that your app is configured as the escalation partner before using this scenario.
Follow the public [Thread Control reference](https://developers.facebook.com/documentation/meta-business-agent/reference/operate/thread-control-cloud-api)
and [support guide](https://developers.facebook.com/documentation/meta-business-agent/support)
if the required configuration is unclear. This kit does not assume a registration mechanism.

Once registered, your app can:

**Take control (before a human sends any message):**

```bash
curl -X POST "https://api.facebook.com/business/whatsapp/phone_numbers/$ENTITY_ID/thread_control" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-API-Version: 1.0.0" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "action": "take",
    "to": "<CONSUMER_PHONE_NUMBER>",
    "metadata": "Human agent stepping in"
  }'
```

MBA stops responding. The user's messages now arrive on the `messages` field of your app.

**Pass control to MBA without sending a message:**

```bash
curl -X POST "https://api.facebook.com/business/whatsapp/phone_numbers/$ENTITY_ID/thread_control" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-API-Version: 1.0.0" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "action": "pass",
    "to": "<CONSUMER_PHONE_NUMBER>",
    "control_pass": {"target_role": "ai_agent"}
  }'
```

`action: "pass"` with `target_role: "ai_agent"` hands control explicitly to MBA. Use this when
you want to return control without sending a message to the user.

**Release (same as Scenario A):**

```bash
curl -X POST "https://api.facebook.com/business/whatsapp/phone_numbers/$ENTITY_ID/thread_control" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-API-Version: 1.0.0" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "action": "release",
    "to": "<CONSUMER_PHONE_NUMBER>"
  }'
```

---

## The messaging_handovers webhook

Both scenarios produce `messaging_handovers` events when control changes. Your app should handle
them to track state:

```json
{
  "type": "control_taken",
  "control_taken": {
    "previous_owner_app_id": "<APP_ID>",
    "new_owner_app_id": "<APP_ID>",
    "new_owner_business_id": "<BUSINESS_ID>",
    "metadata": "Human agent stepping in"
  }
}
```

This webhook goes only to the app that **lost** control, not to all subscribers.

---

## Which action to use

| You want to | Action |
|---|---|
| Step in and send a message | Send a message — control transfers automatically |
| Step in before sending anything (escalation partner only) | `take` |
| Hand back to MBA after a message | `release` |
| Hand back to MBA without sending a message | `pass` with `target_role: "ai_agent"` |

---

## When it goes wrong

| Symptom | Cause |
|---|---|
| `take` returns an error | Your app is not configured as the escalation partner. Use Scenario A instead. |
| `release` returns "you don't hold control" | MBA already holds control — nothing to release. |
| User messages arrive on `messages` when you expect `standby` | Your app sent a message and took control. Release when done. |
| `messaging_handovers` events not arriving | Webhook field not subscribed. Check Step 1. |
