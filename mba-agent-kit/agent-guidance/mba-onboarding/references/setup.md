# Setup

Use the public [Get API key guide](https://developers.facebook.com/documentation/meta-business-agent/get-api-key)
and [end-to-end setup guide](https://developers.facebook.com/documentation/meta-business-agent/get-started)
for account, app and token requirements. This kit does not define an additional access process
or promise an approval lead time.

## Choose the credential model

- **Your own business:** use a system user token for your app and WhatsApp Business account.
- **A client account:** use a Business Integration System User (BISU) token as described in
  the public [BISU documentation](https://developers.facebook.com/documentation/business-messaging/whatsapp/access-tokens/#business-integration-system-user-access-tokens).
  Confirm the client has granted the required assets and permissions. Do not request account
  passwords or ask anyone to paste tokens into a conversation.

If both documented permissions are present but an endpoint still returns empty data, ask the
operator to contact their Meta representative to confirm the app's access, as the public
credentials guide recommends.

## Account-owner checklist

Have the operator confirm:

1. The WhatsApp Business phone number is eligible for Meta Business Agent.
2. The Meta Business Agent Terms of Service are accepted for the WABA.
3. The app and WABA are assigned to the system user or business integration as required by
   the applicable public setup guide.
4. The token has both `whatsapp_business_messaging` and `whatsapp_business_management`.
5. The correct business phone number ID is available; it is not the WABA ID or E.164 number.
6. A payment method is configured before customer delivery requiring billing. The public guide
   permits testing with an allowlisted audience before adding the agent payment method.

Only the account administrator should confirm account changes and consent. Do not make those
changes as an implicit part of configuring the agent.

## Generate and store a system user token

For an own-business system user, follow the public credentials guide:

1. Open [Business Settings](https://business.facebook.com/settings/), then Users → System users.
2. Select the system user with the required assets assigned.
3. Choose **Generate new token**, select the app and token expiration, then select both
   documented permissions.
4. Generate the token and save it securely; it is shown only once.
5. Open `.env` privately and set `MBA_TOKEN` and `MBA_ENTITY_ID`.

For client integrations, follow the linked BISU token instructions instead. Token generation
and storage belong to the operator; the assistant never reads `.env` or echoes credentials.

## Diagnose access using documented responses

The public credentials guide distinguishes these cases:

- Missing messaging permission prevents authentication.
- Missing management permission can produce successful read calls with empty results.
- Terms not accepted for the WABA can produce `403`.
- Some endpoints require additional Meta-granted access; use the public support guidance if
  the documented permissions and account prerequisites are satisfied.

Do not infer approval status from a single response or promise how long a review will take.
Do not automatically retry a failed write.

## Verify

Run `mba doctor` after credentials are stored. Review its target, configuration and eligibility
checks. A doctor result is not launch approval: the go-live gate requires the applicable complete
suite and supported target configuration.
