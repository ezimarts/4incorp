import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import boto3


dynamodb = boto3.resource("dynamodb")
secretsmanager = boto3.client("secretsmanager")

APPLICATIONS_TABLE = dynamodb.Table(os.environ["APPLICATIONS_TABLE"])
PAYMENTS_TABLE = dynamodb.Table(os.environ["PAYMENTS_TABLE"])
EVENTS_TABLE = dynamodb.Table(os.environ["EVENTS_TABLE"])

STRIPE_SECRET_ARN = os.environ["STRIPE_SECRET_ARN"]
STRIPE_SUCCESS_URL = os.environ["STRIPE_SUCCESS_URL"]
STRIPE_CANCEL_URL = os.environ["STRIPE_CANCEL_URL"]
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")

_secret_cache = None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Headers": "Authorization,Content-Type,Stripe-Signature",
            "Access-Control-Allow-Methods": "OPTIONS,POST",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body),
    }


def body_bytes(event):
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(raw)
    return raw.encode("utf-8")


def json_body(event):
    raw = body_bytes(event)
    return json.loads(raw.decode("utf-8") or "{}")


def get_stripe_secrets():
    global _secret_cache
    if _secret_cache is not None:
        return _secret_cache

    result = secretsmanager.get_secret_value(SecretId=STRIPE_SECRET_ARN)
    secret_string = result.get("SecretString")
    if not secret_string:
        raise RuntimeError("Stripe secret must be stored as a JSON SecretString")

    parsed = json.loads(secret_string)
    secret_key = parsed.get("secret_key") or parsed.get("stripe_secret_key")
    webhook_secret = parsed.get("webhook_secret") or parsed.get("stripe_webhook_secret")
    if not secret_key:
        raise RuntimeError("Stripe secret JSON is missing 'secret_key'")

    _secret_cache = {
        "secret_key": secret_key,
        "webhook_secret": webhook_secret or "",
    }
    return _secret_cache


def stripe_request(path, fields):
    secrets = get_stripe_secrets()
    encoded = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.stripe.com/v1/{path.lstrip('/')}",
        data=encoded,
        method="POST",
        headers={
            "Authorization": f"Bearer {secrets['secret_key']}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as result:
            return json.loads(result.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Stripe API error ({error.code}): {payload}") from error


def verify_webhook_signature(payload, signature_header, secret, tolerance=300):
    if not secret or not signature_header:
        return False

    timestamp = None
    signatures = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)

    if not timestamp or not signatures:
        return False

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False

    if abs(int(time.time()) - timestamp_int) > tolerance:
        return False

    signed_payload = timestamp.encode("utf-8") + b"." + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, supplied) for supplied in signatures)


def create_checkout(event):
    body = json_body(event)
    application_id = str(body.get("application_id") or "").strip()
    amount_cents = body.get("amount_cents")
    description = str(body.get("description") or "4incorp business formation service").strip()

    if not application_id:
        return response(400, {"message": "application_id is required"})

    try:
        amount_cents = int(amount_cents)
    except (TypeError, ValueError):
        return response(400, {"message": "amount_cents must be an integer"})

    if amount_cents < 50:
        return response(400, {"message": "amount_cents must be at least 50"})

    application = APPLICATIONS_TABLE.get_item(
        Key={"application_id": application_id},
        ConsistentRead=True,
    ).get("Item")
    if not application:
        return response(404, {"message": "Application not found"})

    fields = {
        "mode": "payment",
        "success_url": STRIPE_SUCCESS_URL,
        "cancel_url": STRIPE_CANCEL_URL,
        "client_reference_id": application_id,
        "metadata[application_id]": application_id,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(amount_cents),
        "line_items[0][price_data][product_data][name]": description,
    }

    customer_email = str(application.get("customer_email") or "").strip()
    if customer_email:
        fields["customer_email"] = customer_email

    session = stripe_request("checkout/sessions", fields)
    session_id = session["id"]
    created_at = now_iso()

    PAYMENTS_TABLE.put_item(
        Item={
            "payment_id": session_id,
            "application_id": application_id,
            "provider": "stripe",
            "status": "Pending",
            "amount_cents": amount_cents,
            "currency": "usd",
            "checkout_url": session.get("url", ""),
            "created_at": created_at,
            "updated_at": created_at,
        }
    )

    return response(
        200,
        {
            "session_id": session_id,
            "checkout_url": session.get("url"),
        },
    )


def record_event(event_object):
    event_id = str(event_object.get("id") or "")
    event_type = str(event_object.get("type") or "unknown")
    data_object = event_object.get("data", {}).get("object", {})
    application_id = str(
        data_object.get("client_reference_id")
        or data_object.get("metadata", {}).get("application_id")
        or "unknown"
    )

    if not event_id:
        return

    EVENTS_TABLE.put_item(
        Item={
            "application_id": application_id,
            "event_id": event_id,
            "event_type": event_type,
            "provider": "stripe",
            "created_at": now_iso(),
        },
        ConditionExpression="attribute_not_exists(event_id)",
    )


def update_payment_from_checkout(session, event_type):
    session_id = str(session.get("id") or "")
    if not session_id:
        return

    status = "Pending"
    if event_type == "checkout.session.completed":
        status = "Paid" if session.get("payment_status") == "paid" else "Completed"
    elif event_type in {"checkout.session.expired", "checkout.session.async_payment_failed"}:
        status = "Failed"
    elif event_type == "checkout.session.async_payment_succeeded":
        status = "Paid"

    PAYMENTS_TABLE.update_item(
        Key={"payment_id": session_id},
        UpdateExpression="SET #status = :status, updated_at = :updated_at, stripe_payment_status = :stripe_payment_status",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": status,
            ":updated_at": now_iso(),
            ":stripe_payment_status": str(session.get("payment_status") or ""),
        },
    )


def webhook(event):
    payload = body_bytes(event)
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    signature = headers.get("stripe-signature", "")
    webhook_secret = get_stripe_secrets().get("webhook_secret", "")

    if not verify_webhook_signature(payload, signature, webhook_secret):
        return response(400, {"message": "Invalid Stripe signature"})

    event_object = json.loads(payload.decode("utf-8"))

    try:
        record_event(event_object)
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return response(200, {"received": True, "duplicate": True})

    event_type = str(event_object.get("type") or "")
    if event_type in {
        "checkout.session.completed",
        "checkout.session.expired",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
    }:
        update_payment_from_checkout(event_object.get("data", {}).get("object", {}), event_type)

    return response(200, {"received": True})


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath") or event.get("path") or "/"

    if method == "OPTIONS":
        return response(204, {})

    try:
        if method == "POST" and path.endswith("/payments/checkout"):
            return create_checkout(event)
        if method == "POST" and path.endswith("/payments/webhook"):
            return webhook(event)
        return response(404, {"message": "Route not found"})
    except json.JSONDecodeError:
        return response(400, {"message": "Invalid JSON body"})
    except Exception as error:
        print(f"Stripe Lambda error: {error}")
        return response(500, {"message": "Payment service error"})
