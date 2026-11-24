# Preflight

Establish that the setup is ready and you can act on the account, **before** anything writes.

Preflight is read-only and safe to run at any time. Run it at the start of an engagement, and run
it again first whenever something has stopped working — most "the agent is not responding" reports
are a failed prerequisite rather than a configuration problem.

Report what is missing rather than working around it. Every prerequisite below is fixable by
exactly one party, and discovering a missing one at rollout wastes days.

## Start with `mba doctor`

```bash
mba doctor
```

This runs the core checks automatically: credentials, eligibility, onboarding status, and the
go-live gate. Fix everything it reports before continuing.

Exit codes:
- **0** — all checks pass
- **3** — a person must act (accept terms, generate a token, grant access) — tell them exactly what
  to click

The go-live gate checks the target, current live configuration, complete canonical evaluation
suite and successful configuration-change record. It is informational in `mba doctor`, so
initial configuration can proceed while the agent is disabled. It blocks `mba enable` and
untested widening of an enabled agent's audience. Changing behavior or credentials requires
disabling an enabled agent first. For versioned targets the prototype gate remains closed:
only documented read/rollback operations are supported, and the public API does not establish
experiment-rule coverage for launch. Do not treat this as an access failure or bypass it.

If `mba` is not installed, run `python3 -m mba doctor` from the kit directory instead.

## Resolve the entity ID first

Everything depends on it. Accept whatever the operator gives and guide them to the right value.

**If they give a human-readable phone number** (e.g. +1 415-555-0100):

> "I need the phone number ID, not the number itself. Find it in WhatsApp Manager:
> 1. Go to [WhatsApp Manager](https://business.facebook.com/latest/whatsapp_manager/)
> 2. Account tools → Phone numbers
> 3. The ID is the long numeric value in the ID column next to your number."

Then set it: open `.env` and set `MBA_ENTITY_ID=your_phone_number_id`.

**If they give a WABA ID:** resolve the phone number ID via API, then ask which number to use if
there is more than one. Set `MBA_ENTITY_ID` in `.env`.

`entity_id` is the **WhatsApp Business phone number ID**. Not the WABA ID, not the business
portfolio ID, not the phone number itself. Using the wrong one produces a `404` that reads as
though the agent does not exist.

Do not run `mba doctor` until `MBA_ENTITY_ID` is set in `.env`.

## Manual checks (what `mba doctor` does not cover)

### Check — Token scopes and account access

```bash
curl -X GET "https://graph.facebook.com/v20.0/debug_token?input_token=$MBA_TOKEN" \
  -H "Authorization: Bearer $MBA_TOKEN"
```

Look for:
- `"is_valid": true` — if false, the token is expired or invalid. Regenerate it.
- `"scopes"` contains both `whatsapp_business_messaging` and `whatsapp_business_management`
- `"granular_scopes"` — find the entry for `whatsapp_business_messaging` and confirm the target
  account's WABA ID appears in `target_ids`. If not, access was never granted.

### Check — App subscribed to the WABA

```bash
curl -X GET "https://graph.facebook.com/v20.0/$WABA_ID/subscribed_apps" \
  -H "Authorization: Bearer $MBA_TOKEN"
```

Your app ID should appear in the list.

### Check — Webhook fields subscribed

Verify in the app dashboard — this cannot be checked via API:

1. Go to [developers.facebook.com/apps](https://developers.facebook.com/apps/) → open your app
2. Left nav → **WhatsApp → Configuration**
3. In **Webhook fields**, confirm `messages`, `standby`, and `messaging_handovers` are each
   subscribed.

App subscription and webhook fields are **different steps in different places**. Completing one
does not complete the other. Without `standby` and `messaging_handovers`, the app is blind to
conversations while MBA holds thread control.

### Check — Agent already exists?

```bash
mba doctor
```

The doctor output includes onboarding status. If the agent is already onboarded, `mba pull` to
export its current config before making any changes.

If the agent is onboarded **and enabled**, say so plainly: **the agent is live and talking to real
customers right now.** Every subsequent write in this session changes a production system.

## What preflight cannot check

Billing requirements are described in the public
[requirements guide](https://developers.facebook.com/documentation/meta-business-agent/requirements).
Ask the account owner to confirm the payment method required for customer delivery.
Testing behind `ALLOWLISTED_ONLY` can proceed before adding the agent payment method.
Do not infer undocumented delivery checks or silent-routing mechanisms from a missing reply;
use the public troubleshooting and support guides.

## Eligibility failures

A number is eligible only if the account is in a supported vertical, is on the WhatsApp Business
Platform (not the WhatsApp Business app), is in good standing, is in an eligible country, meets
business verification requirements, and is not running a conflicting messaging product.

Excluded verticals include finance, government, health, alcohol, gambling, over-the-counter drugs
and matrimony services. See the published overview for the current list.

**Say this early.** An ineligible number does not become eligible because the engagement is
important. The one commonly recoverable case is "not managed through the WhatsApp Business Platform"
— a client on the WhatsApp Business app can migrate. Treat the rest as terminal unless the account
owner says otherwise.

## Terms of Service

If `mba doctor` reports a 403 mentioning Terms of Service, the account owner has not accepted them
in WhatsApp Manager. Use this URL to go straight to the right page (replace with the actual WABA
ID):

```
https://business.facebook.com/latest/whatsapp_manager/business_ai?asset_id=YOUR_WABA_ID
```

The Meta Business Agent tab only appears when opened by a user with admin access to the business
that owns the WABA.

## Output

Report as a readiness list, not prose. For each item: pass, fail, or unknown; and for each failure,
**who fixes it**. End with the single most important line: whether the agent is currently live.
