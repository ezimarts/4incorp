import base64
import html
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError
import boto3
from boto3.dynamodb.conditions import Key


dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
cognito = boto3.client("cognito-idp")
ses = boto3.client("ses")

CLIENTS_TABLE = dynamodb.Table(os.environ["CLIENTS_TABLE"])
CENTRAL_COUNTERS_ENABLED = os.environ.get("CENTRAL_COUNTERS_ENABLED", "false").lower() == "true"
COUNTERS_TABLE = dynamodb.Table(os.environ["COUNTERS_TABLE"]) if os.environ.get("COUNTERS_TABLE") else None
APPLICATIONS_TABLE = dynamodb.Table(os.environ["APPLICATIONS_TABLE"])
DOCUMENTS_TABLE = dynamodb.Table(os.environ["DOCUMENTS_TABLE"])
PAYMENTS_TABLE = dynamodb.Table(os.environ["PAYMENTS_TABLE"])
MESSAGES_TABLE = dynamodb.Table(os.environ["MESSAGES_TABLE"])

DOCUMENT_BUCKET = os.environ["DOCUMENT_BUCKET"]
CLIENT_RECORDS_BUCKET = os.environ["CLIENT_RECORDS_BUCKET"]
APP_SECRET = os.environ["APP_SECRET"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@4incorp.com").lower()
STAFF_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("STAFF_EMAILS", "").split(",")
    if email.strip()
}
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
COGNITO_CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]
COGNITO_USER_POOL = os.environ["COGNITO_USER_POOL"]
APPLICATION_RECEIPT_FROM_EMAIL = os.environ.get("APPLICATION_RECEIPT_FROM_EMAIL", "").strip()
APPLICATION_RECEIPT_REPLY_TO_EMAIL = os.environ.get("APPLICATION_RECEIPT_REPLY_TO_EMAIL", "").strip()
ORDER_COUNTER_KEY = "__ORDER_COUNTER__"
CLIENT_COUNTER_KEY = "__CLIENT_COUNTER__"



INTAKE_BUCKET = "4incorp.com-client-intake-forms"
STATE_NAMES = {'alabama': 'Alabama', 'alaska': 'Alaska', 'arizona': 'Arizona', 'arkansas': 'Arkansas', 'california': 'California', 'colorado': 'Colorado', 'connecticut': 'Connecticut', 'delaware': 'Delaware', 'florida': 'Florida', 'georgia': 'Georgia', 'hawaii': 'Hawaii', 'idaho': 'Idaho', 'illinois': 'Illinois', 'indiana': 'Indiana', 'iowa': 'Iowa', 'kansas': 'Kansas', 'kentucky': 'Kentucky', 'louisiana': 'Louisiana', 'maine': 'Maine', 'maryland': 'Maryland', 'massachusetts': 'Massachusetts', 'michigan': 'Michigan', 'minnesota': 'Minnesota', 'mississippi': 'Mississippi', 'missouri': 'Missouri', 'montana': 'Montana', 'nebraska': 'Nebraska', 'nevada': 'Nevada', 'new hampshire': 'New Hampshire', 'new jersey': 'New Jersey', 'new mexico': 'New Mexico', 'new york': 'New York', 'north carolina': 'North Carolina', 'north dakota': 'North Dakota', 'ohio': 'Ohio', 'oklahoma': 'Oklahoma', 'oregon': 'Oregon', 'pennsylvania': 'Pennsylvania', 'rhode island': 'Rhode Island', 'south carolina': 'South Carolina', 'south dakota': 'South Dakota', 'tennessee': 'Tennessee', 'texas': 'Texas', 'utah': 'Utah', 'vermont': 'Vermont', 'virginia': 'Virginia', 'washington': 'Washington', 'west virginia': 'West Virginia', 'wisconsin': 'Wisconsin', 'wyoming': 'Wyoming', 'al': 'Alabama', 'ak': 'Alaska', 'az': 'Arizona', 'ar': 'Arkansas', 'ca': 'California', 'co': 'Colorado', 'ct': 'Connecticut', 'de': 'Delaware', 'fl': 'Florida', 'ga': 'Georgia', 'hi': 'Hawaii', 'id': 'Idaho', 'il': 'Illinois', 'in': 'Indiana', 'ia': 'Iowa', 'ks': 'Kansas', 'ky': 'Kentucky', 'la': 'Louisiana', 'me': 'Maine', 'md': 'Maryland', 'ma': 'Massachusetts', 'mi': 'Michigan', 'mn': 'Minnesota', 'ms': 'Mississippi', 'mo': 'Missouri', 'mt': 'Montana', 'ne': 'Nebraska', 'nv': 'Nevada', 'nh': 'New Hampshire', 'nj': 'New Jersey', 'nm': 'New Mexico', 'ny': 'New York', 'nc': 'North Carolina', 'nd': 'North Dakota', 'oh': 'Ohio', 'ok': 'Oklahoma', 'or': 'Oregon', 'pa': 'Pennsylvania', 'ri': 'Rhode Island', 'sc': 'South Carolina', 'sd': 'South Dakota', 'tn': 'Tennessee', 'tx': 'Texas', 'ut': 'Utah', 'vt': 'Vermont', 'va': 'Virginia', 'wa': 'Washington', 'wv': 'West Virginia', 'wi': 'Wisconsin', 'wy': 'Wyoming'}

def intake_state(value):
    state = STATE_NAMES.get(str(value).strip().lower())
    if not state:
        raise ValueError("Select a valid US state of registration")
    return state

def intake_component(value):
    value = str(value)
    if not value or not all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in value):
        raise ValueError("Invalid client or application identifier")
    return value

def intake_prefix(application):
    return "/".join((intake_state(application["formation_state"]),
                     intake_component(application["user_id"]),
                     intake_component(application["application_id"]))) + "/"

def intake_text(application):
    """Render the complete intake record as readable UTF-8 text."""
    lines = ["4INCORP Intake Application", "=========================", ""]

    def append_value(label, value, indent=0):
        prefix = " " * indent
        if isinstance(value, dict):
            lines.append(f"{prefix}{label}:" + (" (empty)" if not value else ""))
            for key, child in value.items():
                append_value(str(key), child, indent + 2)
        elif isinstance(value, (list, tuple)):
            lines.append(f"{prefix}{label}:" + (" (empty)" if not value else ""))
            for index, child in enumerate(value, 1):
                append_value(str(index), child, indent + 2)
        else:
            text = "" if value is None else ("Yes" if value is True else "No" if value is False else str(value))
            parts = text.splitlines() or [""]
            lines.append(f"{prefix}{label}: {parts[0]}")
            lines.extend(f"{prefix}  {part}" for part in parts[1:])

    for key, value in application.items():
        append_value(str(key), value)
    return "\n".join(lines) + "\n"


def initialize_intake(application):
    prefix = intake_prefix(application)
    application["intake_prefix"] = prefix
    application["form_record_bucket"] = INTAKE_BUCKET
    application["form_record_key"] = prefix + "intake/application.txt"
    for folder in ("intake", "documents", "correspondence", "receipts", "completed"):
        s3.put_object(Bucket=INTAKE_BUCKET, Key=prefix + folder + "/", Body=b"",
                      ServerSideEncryption="AES256")
    s3.put_object(Bucket=INTAKE_BUCKET, Key=application["form_record_key"],
                  Body=intake_text(application).encode("utf-8"),
                  ContentType="text/plain; charset=utf-8", ServerSideEncryption="AES256")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return str(value)


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Headers": "Authorization,Content-Type",
            "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PATCH,DELETE",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body, default=json_default),
    }


def body_from_event(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    return json.loads(raw or "{}")


def route_from_event(event):
    method = event.get("requestContext", {}).get("http", {}).get("method")
    path = event.get("rawPath") or event.get("path") or "/"
    stage = event.get("requestContext", {}).get("stage")
    if stage and path.startswith(f"/{stage}/"):
        path = path[len(stage) + 1 :]
    return method or event.get("httpMethod", "GET"), "/" + path.strip("/")


def b64url_encode(value):
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def b64url_decode(value):
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000,
    )
    return f"pbkdf2_sha256${salt}${b64url_encode(digest)}"


def verify_password(password, stored):
    try:
        algorithm, salt, supplied = stored.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    expected = hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(expected, supplied)


def token_for(user):
    payload = {
        "sub": user["user_id"],
        "email": user["email"],
        "role": user.get("role", "customer"),
        "name": user.get("name", ""),
        "exp": int(time.time()) + 60 * 60 * 12,
    }
    encoded_payload = b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(
        APP_SECRET.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{b64url_encode(signature)}"


def actor_from_event(event):
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    if not claims:
        return None
    groups = claims.get("cognito:groups", "")
    if isinstance(groups, str):
        groups = [group.strip() for group in groups.strip("[]").split(",") if group.strip()]
    lowered = {str(group).lower() for group in groups}
    role = "admin" if "admin" in lowered else "staff" if "staff" in lowered else "customer"
    return {
        "sub": claims.get("sub", ""),
        "email": str(claims.get("email", "")).lower(),
        "name": claims.get("name", ""),
        "role": role,
    }


def require_actor(event, roles=None):
    actor = actor_from_event(event)
    if not actor:
        return None, response(401, {"message": "Sign in required"})
    if roles and actor.get("role") not in roles:
        return None, response(403, {"message": "You do not have access"})
    return actor, None


def client_by_email(email):
    result = CLIENTS_TABLE.query(
        IndexName="email-index",
        KeyConditionExpression=Key("email").eq(email.lower()),
        Limit=1,
    )
    items = result.get("Items", [])
    return items[0] if items else None


def next_central_number(table):
    # Fail closed until the migration has seeded this sequence. Never reset it.
    if COUNTERS_TABLE is None:
        raise RuntimeError("Central counter storage is not configured")
    result = COUNTERS_TABLE.update_item(
        Key={"counter_name": table.name},
        UpdateExpression="SET last_assigned=last_assigned+:one",
        ConditionExpression="attribute_exists(last_assigned)",
        ExpressionAttributeValues={":one": 1}, ReturnValues="UPDATED_NEW")
    return int(result["Attributes"]["last_assigned"])


def next_client_id():
    if CENTRAL_COUNTERS_ENABLED:
        return next_central_number(CLIENTS_TABLE)
    result = CLIENTS_TABLE.update_item(
        Key={"user_id": CLIENT_COUNTER_KEY},
        UpdateExpression="SET #last_client_id = if_not_exists(#last_client_id, :start) + :inc, #record_type = :record_type, #updated_at = :updated_at",
        ExpressionAttributeNames={
            "#last_client_id": "last_client_id",
            "#record_type": "record_type",
            "#updated_at": "updated_at",
        },
        ExpressionAttributeValues={
            ":start": 100,
            ":inc": 1,
            ":record_type": "counter",
            ":updated_at": now_iso(),
        },
        ReturnValues="UPDATED_NEW",
    )
    return int(result["Attributes"]["last_client_id"])


def ensure_client_id(user):
    if user.get("client_id") is not None:
        return user
    candidate = next_client_id()
    result = CLIENTS_TABLE.update_item(
        Key={"user_id": user["user_id"]},
        UpdateExpression="SET client_id = if_not_exists(client_id, :client_id), cognito_sub = if_not_exists(cognito_sub, :cognito_sub), updated_at = :updated_at",
        ExpressionAttributeValues={
            ":client_id": candidate,
            ":cognito_sub": user["user_id"],
            ":updated_at": now_iso(),
        },
        ReturnValues="ALL_NEW",
    )
    return result["Attributes"]


def public_user(user):
    return {
        "client_id": int(user["client_id"]) if user.get("client_id") is not None else None,
        "email": user["email"],
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "name": user.get("name", ""),
        "phone": user.get("phone", ""),
        "role": user.get("role", "customer"),
        "status": user.get("status", "active"),
        "created_at": user.get("created_at", ""),
    }


def register(body):
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    first_name = str(body.get("firstName") or body.get("first_name") or "").strip()
    last_name = str(body.get("lastName") or body.get("last_name") or "").strip()
    phone = str(body.get("phone", "")).strip()
    if not email or "@" not in email:
        return response(400, {"message": "A valid email is required"})
    if (len(password) < 12 or not any(c.islower() for c in password)
            or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password)
            or not any(not c.isalnum() and not c.isspace() for c in password)):
        return response(400, {"message": "Use 12 or more characters including uppercase, lowercase, a number and a symbol"})
    if not first_name or not last_name:
        return response(400, {"message": "First and last names are required"})
    try:
        result = cognito.sign_up(
            ClientId=COGNITO_CLIENT_ID,
            Username=email,
            Password=password,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "given_name", "Value": first_name},
                {"Name": "family_name", "Value": last_name},
                {"Name": "custom:phone", "Value": phone},
            ],
        )
    except cognito.exceptions.UsernameExistsException:
        return response(409, {"message": "An account with this email already exists"})
    user = {
        "user_id": result["UserSub"],
        "cognito_sub": result["UserSub"],
        "client_id": next_client_id(),
        "email": email,
        "phone": phone,
        "first_name": first_name,
        "last_name": last_name,
        "name": " ".join([first_name, last_name]).strip(),
        "role": "customer",
        "status": "pending_confirmation",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    CLIENTS_TABLE.put_item(Item=user, ConditionExpression="attribute_not_exists(user_id)")
    return response(201, {"user": public_user(user), "confirmation_required": not result.get("UserConfirmed", False)})


def create_account_application(event):
    body = body_from_event(event)
    email = str(body.get("customerEmail") or body.get("email") or "").strip().lower()
    password = str(body.get("accountPassword") or body.get("password") or "")
    if not email or not password:
        return response(400, {"message": "Email and account password are required"})

    registration = register({
        "email": email,
        "password": password,
        "firstName": body.get("firstName", ""),
        "lastName": body.get("lastName", ""),
        "phone": body.get("phone", ""),
    })
    if registration["statusCode"] == 409:
        return response(409, {"message": "An account with this email already exists. Please sign in before submitting this application."})
    if registration["statusCode"] >= 400:
        return registration

    client = client_by_email(email)
    if not client:
        return response(500, {"message": "Account was created but the client record was not found"})
    client = ensure_client_id(client)
    actor = {
        "sub": client["user_id"],
        "email": client["email"],
        "role": "customer",
        "name": client.get("name", ""),
    }

    try:
        application = application_from_body(body, actor)
        intake_prefix(application)
    except ValueError as error:
        return response(400, {"message": str(error)})

    initialize_intake(application)
    APPLICATIONS_TABLE.put_item(Item=application,
        ConditionExpression="attribute_not_exists(application_id)")
    send_application_receipt(application)

    registration_body = json.loads(registration["body"])
    return response(201, {
        "application": application,
        "reference": application["reference"],
        "order_id": application["order_id"],
        "user": registration_body.get("user"),
        "confirmation_required": registration_body.get("confirmation_required", True),
    })


def sync_authenticated_client(access_token):
    # Cognito, not an untrusted decoded JWT or request email, supplies identity.
    result = cognito.get_user(AccessToken=access_token)
    attrs = {a["Name"]: a["Value"] for a in result["UserAttributes"]}
    if not attrs.get("sub") or attrs.get("email_verified") != "true":
        raise ValueError("Verify your email before signing in")
    first, last = attrs.get("given_name", ""), attrs.get("family_name", "")
    values = {":email": attrs["email"].lower(), ":first": first, ":last": last,
        ":name": " ".join([first, last]).strip(), ":phone": attrs.get("custom:phone", ""),
        ":sub": attrs["sub"], ":status": "active", ":role": "customer", ":now": now_iso()}
    user = CLIENTS_TABLE.update_item(Key={"user_id": attrs["sub"]},
        UpdateExpression="SET email=:email, first_name=:first, last_name=:last, #name=:name, phone=:phone, cognito_sub=:sub, #status=:status, #role=if_not_exists(#role,:role), created_at=if_not_exists(created_at,:now), updated_at=:now",
        ExpressionAttributeNames={"#name":"name", "#status":"status", "#role":"role"},
        ExpressionAttributeValues=values, ReturnValues="ALL_NEW")["Attributes"]
    return ensure_client_id(user)


def login(body):
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not email or not password:
        return response(400, {"message": "Email and password are required"})
    result = cognito.initiate_auth(ClientId=COGNITO_CLIENT_ID,
        AuthFlow="USER_PASSWORD_AUTH", AuthParameters={"USERNAME":email,"PASSWORD":password})
    auth = result.get("AuthenticationResult", {})
    if not auth.get("AccessToken") or not auth.get("IdToken"):
        return response(409, {"message": "This account requires an additional authentication step; contact support", "code":"AUTH_CHALLENGE_REQUIRED"})
    try:
        user = sync_authenticated_client(auth["AccessToken"])
    except ValueError as error:
        return response(403, {"message": str(error)})
    return response(200, {"client_id": user["client_id"], "user": public_user(user),
        "access_token": auth["AccessToken"], "id_token": auth["IdToken"],
        "expires_in": auth.get("ExpiresIn")})


def resend_confirmation(body):
    email = str(body.get("email", "")).strip().lower()
    if not email:
        return response(400, {"message": "Email is required"})
    cognito.resend_confirmation_code(ClientId=COGNITO_CLIENT_ID, Username=email)
    return response(200, {"message": "Check your email for a confirmation code"})


def confirm_registration(body):
    email = str(body.get("email", "")).strip().lower()
    code = str(body.get("code", "")).strip()
    if not email or not code:
        return response(400, {"message": "Email and confirmation code are required"})
    cognito.confirm_sign_up(ClientId=COGNITO_CLIENT_ID, Username=email, ConfirmationCode=code)
    user = client_by_email(email)
    if user:
        CLIENTS_TABLE.update_item(
            Key={"user_id": user["user_id"]},
            UpdateExpression="SET #status = :status, updated_at = :updated",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": "active", ":updated": now_iso()},
        )
    return response(200, {"message": "Account confirmed"})


def forgot_password(body):
    email = str(body.get("email", "")).strip().lower()
    cognito.forgot_password(ClientId=COGNITO_CLIENT_ID, Username=email)
    return response(200, {"message": "If the account exists, a recovery code has been sent"})


def confirm_forgot_password(body):
    cognito.confirm_forgot_password(
        ClientId=COGNITO_CLIENT_ID,
        Username=str(body.get("email", "")).strip().lower(),
        ConfirmationCode=str(body.get("code", "")).strip(),
        Password=str(body.get("password", "")),
    )
    return response(200, {"message": "Password updated"})


def next_order_id():
    if CENTRAL_COUNTERS_ENABLED:
        return next_central_number(APPLICATIONS_TABLE)
    result = APPLICATIONS_TABLE.update_item(
        Key={"application_id": ORDER_COUNTER_KEY},
        UpdateExpression="SET #order_id = if_not_exists(#order_id, :start) + :inc, #record_type = :record_type, #updated_at = :updated_at",
        ExpressionAttributeNames={
            "#order_id": "order_id",
            "#record_type": "record_type",
            "#updated_at": "updated_at",
        },
        ExpressionAttributeValues={
            ":start": 100,
            ":inc": 1,
            ":record_type": "counter",
            ":updated_at": now_iso(),
        },
        ReturnValues="UPDATED_NEW",
    )
    return int(result["Attributes"]["order_id"])


def application_reference(order_id):
    return f"4INC-{order_id:06d}"


def application_from_body(body, actor=None):
    customer_email = str(body.get("customerEmail") or body.get("customer_email") or body.get("email") or "").strip().lower()
    first_name = str(body.get("firstName") or body.get("first_name") or "").strip()
    last_name = str(body.get("lastName") or body.get("last_name") or "").strip()
    preferred_name = str(body.get("preferredName") or body.get("preferred_name") or "").strip()
    formation_state = intake_state(body.get("formationState") or body.get("formation_state") or "")
    business_type = str(body.get("businessType") or body.get("business_type") or "").strip()

    missing = [
        label
        for label, value in {
            "firstName": first_name,
            "lastName": last_name,
            "customerEmail": customer_email,
            "phone": body.get("phone"),
            "businessType": business_type,
            "formationState": formation_state,
            "preferredName": preferred_name,
            "businessPurpose": body.get("businessPurpose") or body.get("business_purpose"),
        }.items()
        if not str(value or "").strip()
    ]
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))

    now = now_iso()
    application_id = str(uuid.uuid4())
    order_id = next_order_id()
    client = client_by_email(actor.get("email", "")) if actor else None
    if client:
        client = ensure_client_id(client)
    client_id = str(int(client["client_id"])) if client and client.get("client_id") is not None else (actor.get("sub") if actor else f"guest-{application_id}")
    safe_form = {
        key: value
        for key, value in body.items()
        if key not in {"accountPassword", "confirmPassword", "password"}
    }
    return {
        "application_id": application_id,
        "client_id": client_id,
        "record_type": "ORDER",
        "order_id": order_id,
        "reference": application_reference(order_id),
        "user_id": actor.get("sub", "") if actor else "",
        "customer_email": customer_email,
        "customer_name": " ".join([first_name, last_name]).strip(),
        "phone": str(body.get("phone", "")).strip(),
        "business_type": business_type,
        "formation_state": formation_state,
        "preferred_name": preferred_name,
        "alternate_name": str(body.get("alternateName") or body.get("alternate_name") or "").strip(),
        "owners": int(body.get("owners") or 1),
        "management": str(body.get("management", "")).strip(),
        "start_date": str(body.get("startDate") or body.get("start_date") or "").strip(),
        "ein_help": str(body.get("einHelp") or body.get("ein_help") or "").strip(),
        "business_purpose": str(body.get("businessPurpose") or body.get("business_purpose") or "").strip(),
        "address": {
            "street": str(body.get("streetAddress") or body.get("street_address") or "").strip(),
            "city": str(body.get("city", "")).strip(),
            "state": str(body.get("addressState") or body.get("address_state") or "").strip(),
            "zip": str(body.get("zip") or body.get("postalCode") or body.get("postal_code") or "").strip(),
        },
        "form_data": safe_form,
        "status": "Submitted",
        "assigned_staff_email": "unassigned",
        "submitted_at": now,
        "updated_at": now,
    }


def send_application_receipt(application):
    """Send a receipt after the application has been durably stored."""
    recipient = str(application.get("customer_email") or "").strip()
    if not APPLICATION_RECEIPT_FROM_EMAIL or not recipient:
        return

    customer_name = html.escape(str(application.get("customer_name") or "there"))
    reference = html.escape(str(application.get("reference") or "Not available"))
    business_name = html.escape(str(application.get("preferred_name") or "your business"))
    subject = f"Your 4incorp application has been received{': ' + application['reference'] if application.get('reference') else ''}"
    text_body = (
        f"Hello {application.get('customer_name') or 'there'},\n\n"
        "Thank you for submitting your business registration application with 4incorp.com.\n\n"
        "We have received your application and it is now in process. "
        "Our team will review the information provided and will contact you if any additional details are needed.\n\n"
        "We will keep you posted on the progress of your application.\n\n"
        f"Reference number: {application.get('reference') or 'Not available'}\n\n"
        "Please keep this email for your records.\n\n"
        "Thank you,\nThe 4incorp.com Team\n\n"
        "This is an automated message from a no-reply email address. Please do not reply to this email."
    )
    html_body = f"""<!doctype html>
<html><body style=\"font-family:Arial,sans-serif;line-height:1.5;color:#1f2937\">
  <p>Hello {customer_name},</p>
  <p>Thank you for submitting your business registration application with 4incorp.com.</p>
  <p>We have received your application for <strong>{business_name}</strong> and it is now in process. Our team will review the information provided and will contact you if any additional details are needed.</p>
  <p>We will keep you posted on the progress of your application.</p>
  <p><strong>Reference number:</strong> {reference}</p>
  <p>Please keep this email for your records.</p>
  <p>Thank you,<br>The 4incorp.com Team</p>
  <p style=\"color:#526173;font-size:13px\">This is an automated message from a no-reply email address. Please do not reply to this email.</p>
</body></html>"""
    request = {
        "Source": APPLICATION_RECEIPT_FROM_EMAIL,
        "Destination": {"ToAddresses": [recipient]},
        "Message": {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": text_body, "Charset": "UTF-8"},
                "Html": {"Data": html_body, "Charset": "UTF-8"},
            },
        },
    }
    if APPLICATION_RECEIPT_REPLY_TO_EMAIL:
        request["ReplyToAddresses"] = [APPLICATION_RECEIPT_REPLY_TO_EMAIL]
    try:
        ses.send_email(**request)
    except ClientError as error:
        # A send failure must not make a customer resubmit an application.
        print("Application receipt email failed", application.get("reference", ""),
              error.response.get("Error", {}).get("Code", "Unknown"))


def send_case_update_notification(application, update_type, detail):
    """Send a transactional notification for a customer-visible case event."""
    recipient = str(application.get("customer_email") or "").strip()
    if not APPLICATION_RECEIPT_FROM_EMAIL or not recipient:
        return

    customer_name = str(application.get("customer_name") or "there")
    reference = str(application.get("reference") or "your application")
    if update_type == "status":
        subject = f"4incorp application update: {reference}"
        summary = f"Your application status is now: {detail}."
        heading = "Your application status has been updated"
    else:
        subject = f"New message about your 4incorp application: {reference}"
        summary = "A member of the 4incorp team sent you a message:"
        heading = "You have a new application message"

    text_body = (
        f"Hello {customer_name},\n\n{heading}.\n\n{summary}\n"
        + (f"\n{detail}\n" if update_type == "message" else "")
        + f"\nReference number: {reference}\n\nPlease sign in to your 4incorp account to view your application.\n\n"
          "Thank you,\nThe 4incorp.com Team\n\n"
          "This is an automated transactional message from a no-reply email address."
    )
    escaped_detail = html.escape(str(detail)).replace("\n", "<br>")
    html_body = f"""<!doctype html>
<html><body style=\"font-family:Arial,sans-serif;line-height:1.5;color:#1f2937\">
  <p>Hello {html.escape(customer_name)},</p>
  <p><strong>{html.escape(heading)}</strong></p>
  <p>{html.escape(summary)}</p>
  {f'<p>{escaped_detail}</p>' if update_type == 'message' else ''}
  <p><strong>Reference number:</strong> {html.escape(reference)}</p>
  <p>Please sign in to your 4incorp account to view your application.</p>
  <p>Thank you,<br>The 4incorp.com Team</p>
  <p style=\"color:#526173;font-size:13px\">This is an automated transactional message from a no-reply email address.</p>
</body></html>"""
    request = {
        "Source": APPLICATION_RECEIPT_FROM_EMAIL,
        "Destination": {"ToAddresses": [recipient]},
        "Message": {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": text_body, "Charset": "UTF-8"},
                "Html": {"Data": html_body, "Charset": "UTF-8"},
            },
        },
    }
    if APPLICATION_RECEIPT_REPLY_TO_EMAIL:
        request["ReplyToAddresses"] = [APPLICATION_RECEIPT_REPLY_TO_EMAIL]
    try:
        ses.send_email(**request)
    except ClientError as error:
        print("Case update email failed", reference,
              error.response.get("Error", {}).get("Code", "Unknown"))


def create_application(event):
    actor, error = require_actor(event)
    if error:
        return error
    if not actor.get("sub"):
        return response(401, {"message": "Sign in required"})
    body = body_from_event(event)
    # Clients cannot assign their submission to another email address.
    if actor["role"] == "customer":
        if not actor.get("email"):
            return response(403, {"message": "An authenticated email is required"})
        body["customerEmail"] = actor["email"]
    try:
        application = application_from_body(body, actor)
        intake_prefix(application)
    except ValueError as error:
        return response(400, {"message": str(error)})
    # S3 and DynamoDB are not transactional. Failures must be reconciled;
    # no successful response is sent unless both writes finish.
    initialize_intake(application)
    APPLICATIONS_TABLE.put_item(Item=application,
        ConditionExpression="attribute_not_exists(application_id)")
    send_application_receipt(application)
    return response(201, {"application": application,
        "reference": application["reference"], "order_id": application["order_id"]})


def list_applications(event):
    actor, error = require_actor(event)
    if error:
        return error
    if actor["role"] == "admin":
        items = APPLICATIONS_TABLE.query(
            IndexName="all-orders-index",
            KeyConditionExpression=Key("record_type").eq("ORDER"),
            ScanIndexForward=False,
        ).get("Items", [])
    elif actor["role"] == "staff":
        items = staff_applications(actor)
    else:
        items = APPLICATIONS_TABLE.query(
            IndexName="customer-email-submitted-index",
            KeyConditionExpression=Key("customer_email").eq(actor["email"]),
        ).get("Items", [])
    items = [item for item in items if item.get("application_id") != ORDER_COUNTER_KEY]
    items.sort(key=lambda item: int(item.get("order_id", 0)), reverse=True)
    return response(200, {"applications": items})


def get_application_by_reference(reference):
    result = APPLICATIONS_TABLE.query(
        IndexName="reference-index",
        KeyConditionExpression=Key("reference").eq(reference),
        Limit=1,
    )
    items = result.get("Items", [])
    return items[0] if items else None


def get_application(event, reference):
    actor, error = require_actor(event)
    if error:
        return error
    application = get_application_by_reference(reference)
    if not application:
        return response(404, {"message": "Application not found"})
    if actor["role"] == "staff" and not staff_can_access_application(actor, application):
        return response(403, {"message": "This application is not assigned to you"})
    if actor["role"] == "customer" and application.get("customer_email") != actor["email"]:
        return response(403, {"message": "You cannot view this application"})
    return response(200, {"application": application})


def update_application(event, reference):
    actor, error = require_actor(event, {"admin", "staff"})
    if error:
        return error
    application = get_application_by_reference(reference)
    if not application:
        return response(404, {"message": "Application not found"})
    if actor["role"] == "staff" and not staff_can_access_application(actor, application):
        return response(403, {"message": "This application is not assigned to you"})
    body = body_from_event(event)
    if actor["role"] == "staff":
        if set(body) - {"status", "note"}:
            return response(403, {"message": "Only admins can reassign applications"})
        if "status" in body and body["status"] not in STAFF_APPLICATION_STATUSES:
            return response(400, {"message": "Invalid application status"})
    updates = {}
    for key in ["status", "assigned_staff_email"]:
        if key in body:
            value = str(body[key]).strip()
            updates[key] = value or "unassigned"
    if "note" in body:
        updates["latest_note"] = str(body["note"]).strip()
    if not updates:
        return response(400, {"message": "No supported fields supplied"})
    updates["updated_at"] = now_iso()

    expression = "SET " + ", ".join(f"#{key} = :{key}" for key in updates)
    result = APPLICATIONS_TABLE.update_item(
        Key={"application_id": application["application_id"]},
        UpdateExpression=expression,
        ExpressionAttributeNames={f"#{key}": key for key in updates},
        ExpressionAttributeValues={f":{key}": value for key, value in updates.items()},
        ReturnValues="ALL_NEW",
    )
    updated_application = result["Attributes"]
    if "status" in updates and updates["status"] != application.get("status"):
        send_case_update_notification(updated_application, "status", updates["status"])
    return response(200, {"application": updated_application})


def client_document_prefix(application):
    """Use the account name and immutable client ID from trusted records."""
    import re
    import unicodedata
    client_id = application.get("client_id") or application.get("user_id")
    if not client_id:
        raise ValueError("Application has no client identifier")
    client = {}
    if application.get("user_id"):
        client = CLIENTS_TABLE.get_item(
            Key={"user_id": application["user_id"]}, ConsistentRead=True
        ).get("Item") or {}
    name = client.get("name") or " ".join(
        str(client.get(field) or "").strip() for field in ("first_name", "last_name")
    ).strip() or application.get("customer_name") or "client"
    # Preserve international letters while replacing spaces and path punctuation.
    name = unicodedata.normalize("NFKC", str(name)).casefold()
    name = re.sub(r"[^\w]+", "-", name, flags=re.UNICODE).replace("_", "-")
    name = re.sub(r"-+", "-", name).strip("-")[:80].rstrip("-") or "client"
    return intake_component(client_id) + "/" + name + "/"


def create_document_upload(event, reference):
    actor, error = require_actor(event)
    if error:
        return error
    application = get_application_by_reference(reference)
    if not application:
        return response(404, {"message": "Application not found"})
    if actor["role"] == "staff" and not staff_can_access_application(actor, application):
        return response(403, {"message": "This application is not assigned to you"})
    if actor["role"] == "customer" and (not actor.get("sub") or application.get("user_id") != actor["sub"]):
        return response(403, {"message": "You cannot add documents to this application"})

    body = body_from_event(event)
    file_name = str(body.get("file_name") or body.get("name") or "document").replace("\\", "/").split("/")[-1].strip()
    if not file_name or file_name in {".", ".."} or "${" in file_name or any(ord(c) < 32 for c in file_name):
        return response(400, {"message": "Invalid document filename"})
    content_type = str(body.get("content_type") or "application/octet-stream").strip()
    document_id = str(uuid.uuid4())
    client_id = application.get("client_id") or application.get("user_id") or f"guest-{application['application_id']}"
    try:
        key = client_document_prefix(application) + f"{document_id}/{file_name}"
    except ValueError as error:
        return response(400, {"message": str(error)})
    upload = s3.generate_presigned_post(
        Bucket=DOCUMENT_BUCKET,
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, 15 * 1024 * 1024]],
        ExpiresIn=300,
    )
    item = {
        "document_id": document_id,
        "application_id": application["application_id"],
        "client_id": client_id,
        "reference": reference,
        "name": file_name,
        "content_type": content_type,
        "s3_key": key,
        "s3_bucket": DOCUMENT_BUCKET,
        "user_id": application.get("user_id", ""),
        "status": "Waiting",
        "uploaded_by": actor["email"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    DOCUMENTS_TABLE.put_item(Item=item)
    return response(201, {"document": item, "upload": upload})


def create_message(event, reference):
    actor, error = require_actor(event)
    if error:
        return error
    application = get_application_by_reference(reference)
    if not application:
        return response(404, {"message": "Application not found"})
    if actor["role"] == "staff" and not staff_can_access_application(actor, application):
        return response(403, {"message": "This application is not assigned to you"})
    if actor["role"] == "customer" and application.get("customer_email") != actor["email"]:
        return response(403, {"message": "You cannot message this application"})
    body = body_from_event(event)
    text = str(body.get("message") or body.get("body") or "").strip()
    if not text:
        return response(400, {"message": "Message is required"})
    item = {
        "message_id": str(uuid.uuid4()),
        "application_id": application["application_id"],
        "reference": reference,
        "sender_email": actor["email"],
        "sender_role": actor["role"],
        "message": text,
        "created_at": now_iso(),
    }
    MESSAGES_TABLE.put_item(Item=item)
    if actor["role"] in {"admin", "staff"}:
        send_case_update_notification(application, "message", text)
    return response(201, {"message": item})


def create_payment(event, reference):
    actor, error = require_actor(event, {"admin"})
    if error:
        return error
    application = get_application_by_reference(reference)
    if not application:
        return response(404, {"message": "Application not found"})
    body = body_from_event(event)
    item = {
        "payment_id": str(uuid.uuid4()),
        "application_id": application["application_id"],
        "reference": reference,
        "customer_email": application.get("customer_email", ""),
        "amount": Decimal(str(body.get("amount", "0"))),
        "status": str(body.get("status") or "Pending"),
        "provider": str(body.get("provider") or "manual"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    PAYMENTS_TABLE.put_item(Item=item)
    return response(201, {"payment": item})


def admin_staff():
    users = []
    params = {"UserPoolId": COGNITO_USER_POOL, "GroupName": "Staff", "Limit": 60}
    while True:
        result = cognito.list_users_in_group(**params)
        for user in result.get("Users", []):
            attrs = {a["Name"]: a["Value"] for a in user.get("Attributes", [])}
            if user.get("Enabled") and attrs.get("sub") and attrs.get("email"):
                users.append({"user_id": attrs["sub"], "email": attrs["email"],
                              "name": attrs.get("name") or attrs.get("given_name") or attrs["email"]})
        if not result.get("NextToken"):
            return users
        params["NextToken"] = result["NextToken"]


def task_table():
    # Derive the same stack prefix as the existing applications table.
    name = os.environ["APPLICATIONS_TABLE"]
    return dynamodb.Table(name.removesuffix("-applications") + "-staff-tasks")


def admin_overview(event):
    actor, error = require_actor(event, {"admin"})
    if error:
        return error
    applications = []
    params = {"IndexName": "all-orders-index", "KeyConditionExpression": Key("record_type").eq("ORDER")}
    while True:
        result = APPLICATIONS_TABLE.query(**params)
        applications.extend(result.get("Items", []))
        if not result.get("LastEvaluatedKey"):
            break
        params["ExclusiveStartKey"] = result["LastEvaluatedKey"]
    tasks, params = [], {}
    while True:
        result = task_table().scan(**params)
        tasks.extend(result.get("Items", []))
        if not result.get("LastEvaluatedKey"):
            break
        params["ExclusiveStartKey"] = result["LastEvaluatedKey"]
    # Only dashboard fields; omit intake contents and other client records.
    fields = ("application_id", "reference", "preferred_name", "formation_state", "business_type",
              "status", "customer_name", "assigned_staff_email", "submitted_at", "updated_at")
    return response(200, {"applications": [{k:a.get(k, "") for k in fields} for a in applications],
        "tasks": tasks, "staff": admin_staff(), "fetched_at": now_iso()})


def task_datetime(value):
    value = str(value or "")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Task dates must include a timezone")
    return dt.astimezone(timezone.utc)


def create_admin_task(event):
    actor, error = require_actor(event, {"admin"})
    if error:
        return error
    body = body_from_event(event)
    try:
        title = str(body.get("title", "")).strip()
        if not title or len(title) > 200:
            raise ValueError("Enter a task title of 1–200 characters")
        start, due = task_datetime(body.get("starts_at")), task_datetime(body.get("due_at"))
        if due < start:
            raise ValueError("Due date cannot precede start date")
        staff = next((s for s in admin_staff() if s["user_id"] == body.get("staff_id")), None)
        if not staff:
            raise ValueError("Choose an active member of the Staff group")
        application = get_application_by_reference(str(body.get("reference", "")))
        if not application:
            raise ValueError("Choose an existing business application")
    except (ValueError, TypeError) as exc:
        return response(400, {"message": str(exc)})
    task = {"task_id": str(uuid.uuid4()), "title": title, "staff_id": staff["user_id"],
        "staff_email": staff["email"], "reference": application["reference"],
        "application_id": application["application_id"], "starts_at": start.isoformat(), "due_at": due.isoformat(),
        "status": "Assigned", "version": 1, "created_at": now_iso(), "updated_at": now_iso(),
        "created_by": actor["sub"], "updated_by": actor["sub"]}
    task_table().put_item(Item=task, ConditionExpression="attribute_not_exists(task_id)")
    return response(201, {"task": task})


def update_admin_task(event, task_id):
    actor, error = require_actor(event, {"admin"})
    if error:
        return error
    body = body_from_event(event)
    status = body.get("status")
    if status not in {"Assigned", "In progress", "Blocked", "Completed", "Cancelled"}:
        return response(400, {"message": "Invalid task status"})
    version = body.get("version")
    if type(version) is not int or version < 1:
        return response(400, {"message": "Refresh the task before updating"})
    try:
        result = task_table().update_item(Key={"task_id": task_id},
            UpdateExpression="SET #s=:s, updated_at=:now, updated_by=:actor, #v=:next",
            ConditionExpression="attribute_exists(task_id) AND #v=:old",
            ExpressionAttributeNames={"#s":"status", "#v":"version"},
            ExpressionAttributeValues={":s":status, ":now":now_iso(), ":actor":actor["sub"], ":next":version+1, ":old":version},
            ReturnValues="ALL_NEW")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return response(409, {"message": "Task changed or no longer exists. Refresh and retry."})
        raise
    return response(200, {"task": result["Attributes"]})


STAFF_PERMISSIONS = [
    {"action": "View tasks", "allowed": True, "scope": "Tasks assigned to your account"},
    {"action": "Update task status, progress and work notes", "allowed": True, "scope": "Your open tasks; completed/cancelled tasks require admin reopening"},
    {"action": "View applications and update filing status", "allowed": True, "scope": "Applications assigned directly to you or linked to your active tasks"},
    {"action": "Upload documents and send application messages", "allowed": True, "scope": "Your assigned applications through the existing application API"},
    {"action": "Assign tasks or change deadlines", "allowed": False, "scope": "Admin only"},
    {"action": "Manage staff permissions or payments", "allowed": False, "scope": "Admin only"},
    {"action": "View other staff members' tasks", "allowed": False, "scope": "Admin only"},
]
STAFF_APPLICATION_STATUSES = {"Submitted", "Under Review", "In Process", "Needs Information", "Filed", "Completed"}


def assigned_staff_tasks(actor):
    items, params = [], {"IndexName": "staff-id-index", "KeyConditionExpression": Key("staff_id").eq(actor["sub"])}
    while True:
        result = task_table().query(**params)
        # Re-read the base record: GSI assignment changes are eventually consistent.
        for indexed in result.get("Items", []):
            item = task_table().get_item(Key={"task_id": indexed["task_id"]}, ConsistentRead=True).get("Item")
            if item and item.get("staff_id") == actor["sub"]:
                items.append(item)
        if not result.get("LastEvaluatedKey"):
            return items
        params["ExclusiveStartKey"] = result["LastEvaluatedKey"]


def staff_can_access_application(actor, application, tasks=None):
    if actor.get("email") and application.get("assigned_staff_email", "").lower() == actor["email"].lower():
        return True
    tasks = assigned_staff_tasks(actor) if tasks is None else tasks
    return any(t.get("application_id") == application["application_id"] and t.get("status") not in {"Completed", "Cancelled"} for t in tasks)


def staff_applications(actor, tasks=None):
    tasks = assigned_staff_tasks(actor) if tasks is None else tasks
    ids = {t["application_id"] for t in tasks if t.get("status") not in {"Completed", "Cancelled"}}
    if actor.get("email"):
        params = {"IndexName":"assigned-staff-index", "KeyConditionExpression":Key("assigned_staff_email").eq(actor["email"])}
        while True:
            result = APPLICATIONS_TABLE.query(**params)
            ids.update(a["application_id"] for a in result.get("Items", []))
            if not result.get("LastEvaluatedKey"):
                break
            params["ExclusiveStartKey"] = result["LastEvaluatedKey"]
    applications = []
    for app_id in ids:
        item = APPLICATIONS_TABLE.get_item(Key={"application_id":app_id},ConsistentRead=True).get("Item")
        if item and staff_can_access_application(actor, item, tasks):
            applications.append(item)
    return applications


def staff_overview(event):
    actor, error = require_actor(event, {"staff"})
    if error:
        return error
    tasks = assigned_staff_tasks(actor)
    fields = ("application_id", "reference", "preferred_name", "formation_state", "status", "customer_name", "updated_at")
    applications = [{k:a.get(k, "") for k in fields} for a in staff_applications(actor,tasks)]
    return response(200, {"tasks": tasks, "applications": applications,
        "permissions": STAFF_PERMISSIONS, "application_statuses": sorted(STAFF_APPLICATION_STATUSES),
        "fetched_at": now_iso(), "staff_email": actor.get("email", "")})


def update_staff_task(event, task_id):
    actor, error = require_actor(event, {"staff"})
    if error:
        return error
    body = body_from_event(event)
    if set(body) - {"status", "progress", "note", "version"}:
        return response(403, {"message": "You cannot change assignment, deadlines or task permissions"})
    status, progress, version = body.get("status"), body.get("progress"), body.get("version")
    note = str(body.get("note", "")).strip()
    if status not in {"Assigned", "In progress", "Blocked", "Completed"} or type(progress) is not int or not 0 <= progress <= 100:
        return response(400, {"message": "Choose a valid status and progress from 0 to 100"})
    if type(version) is not int or version < 1 or len(note) > 2000:
        return response(400, {"message": "Invalid task version or note longer than 2000 characters"})
    if (status == "Completed" and progress != 100) or (status != "Completed" and progress == 100):
        return response(400, {"message": "Use 100% only for completed tasks"})
    if status == "Assigned" and progress != 0:
        return response(400, {"message": "Select In progress or Blocked for work already started"})
    if status == "Blocked" and not note:
        return response(400, {"message": "Explain the blocker in the work note"})
    try:
        result = task_table().update_item(Key={"task_id":task_id},
            UpdateExpression="SET #s=:s, progress=:p, work_note=:note, updated_at=:now, updated_by=:owner, #v=:next",
            ConditionExpression="attribute_exists(task_id) AND staff_id=:owner AND #v=:old AND #s<>:completed AND #s<>:cancelled",
            ExpressionAttributeNames={"#s":"status", "#v":"version"},
            ExpressionAttributeValues={":s":status, ":p":progress, ":note":note, ":now":now_iso(),
                ":owner":actor["sub"], ":next":version+1, ":old":version, ":completed":"Completed", ":cancelled":"Cancelled"},
            ReturnValues="ALL_NEW")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return response(409, {"message": "Task changed, is closed or is not assigned to you. Refresh; ask an admin to reopen closed tasks."})
        raise
    return response(200, {"task":result["Attributes"]})


def document_application_access(actor, application):
    if not application:
        return False
    if actor["role"] == "admin":
        return True
    if actor["role"] == "staff":
        return staff_can_access_application(actor, application)
    return bool(actor.get("sub")) and application.get("user_id") == actor["sub"]


def list_client_documents(event):
    actor, error = require_actor(event)
    if error:
        return error
    # Query candidate applications, then verify immutable ownership on base records.
    params = {"IndexName":"customer-email-submitted-index", "KeyConditionExpression":Key("customer_email").eq(actor.get("email", ""))}
    app_ids = set()
    while True:
        result = APPLICATIONS_TABLE.query(**params)
        app_ids.update(a["application_id"] for a in result.get("Items", []))
        if not result.get("LastEvaluatedKey"):
            break
        params["ExclusiveStartKey"] = result["LastEvaluatedKey"]
    docs = []
    for app_id in app_ids:
        application = APPLICATIONS_TABLE.get_item(Key={"application_id":app_id},ConsistentRead=True).get("Item")
        if not application or not actor.get("sub") or application.get("user_id") != actor["sub"]:
            continue
        params = {"IndexName":"application-created-index", "KeyConditionExpression":Key("application_id").eq(app_id)}
        while True:
            result = DOCUMENTS_TABLE.query(**params)
            for item in result.get("Items", []):
                if item.get("application_id") != app_id:
                    continue
                docs.append({"document_id":item["document_id"], "reference":application.get("reference", ""),
                    "name":item.get("name", "Document"), "type":item.get("type") or item.get("content_type", "Document"),
                    "status":item.get("status", "Unknown"), "created_at":item.get("created_at", "")})
            if not result.get("LastEvaluatedKey"):
                break
            params["ExclusiveStartKey"] = result["LastEvaluatedKey"]
    return response(200, {"documents":sorted(docs,key=lambda d:d["created_at"],reverse=True)})


def document_download(event, document_id):
    actor, error = require_actor(event)
    if error:
        return error
    item = DOCUMENTS_TABLE.get_item(Key={"document_id":document_id},ConsistentRead=True).get("Item")
    if not item or not item.get("application_id"):
        return response(404, {"message":"Document not found"})
    application = APPLICATIONS_TABLE.get_item(Key={"application_id":item["application_id"]},ConsistentRead=True).get("Item")
    if not document_application_access(actor,application):
        return response(404, {"message":"Document not found"})
    bucket, key = item.get("s3_bucket"), item.get("s3_key")
    if bucket not in {INTAKE_BUCKET, DOCUMENT_BUCKET, CLIENT_RECORDS_BUCKET} or not key:
        return response(409, {"message":"The document has no valid stored file. Contact support."})
    try:
        metadata = s3.head_object(Bucket=bucket,Key=key)
    except ClientError as exc:
        if exc.response.get("Error",{}).get("Code") in {"404","NoSuchKey","NotFound"}:
            return response(409, {"message":"File upload is not complete or the file is no longer available."})
        return response(503, {"message":"The stored file cannot be accessed right now. Contact support."})
    mode = (event.get("queryStringParameters") or {}).get("mode", "download")
    content_type = metadata.get("ContentType", "application/octet-stream")
    inline = mode == "view" and content_type in {"application/pdf","image/png","image/jpeg","image/gif","image/webp"}
    # Encode the display filename instead of trusting it as a response header.
    from urllib.parse import quote
    name = str(item.get("name") or "document").replace("\\", "/").split("/")[-1]
    disposition = ("inline" if inline else "attachment") + "; filename*=UTF-8''" + quote(name, safe="")
    url = s3.generate_presigned_url("get_object", Params={"Bucket":bucket,"Key":key,
        "ResponseContentDisposition":disposition,"ResponseContentType":content_type},ExpiresIn=120)
    return response(200, {"url":url,"expires_in":120})


def complete_document_upload(event, document_id):
    actor, error = require_actor(event)
    if error:
        return error
    item = DOCUMENTS_TABLE.get_item(Key={"document_id":document_id},ConsistentRead=True).get("Item")
    if not item or not item.get("application_id"):
        return response(404, {"message":"Document not found"})
    application = APPLICATIONS_TABLE.get_item(Key={"application_id":item["application_id"]},ConsistentRead=True).get("Item")
    if not document_application_access(actor,application):
        return response(404, {"message":"Document not found"})
    bucket,key=item.get("s3_bucket"),item.get("s3_key")
    if bucket not in {INTAKE_BUCKET,DOCUMENT_BUCKET,CLIENT_RECORDS_BUCKET} or not key:
        return response(409, {"message":"Invalid document storage record"})
    try:
        metadata=s3.head_object(Bucket=bucket,Key=key)
    except ClientError:
        return response(409, {"message":"Upload could not be verified in storage. Retry confirmation or contact support."})
    if not 0 < metadata.get("ContentLength",0) <= 15*1024*1024:
        return response(400, {"message":"The stored document must be between 1 byte and 15 MB"})
    # Idempotent retry: preserve a later workflow status such as Ready to Download.
    if item.get("status") == "Waiting":
        try:
            result=DOCUMENTS_TABLE.update_item(Key={"document_id":document_id},
                UpdateExpression="SET #s=:received, uploaded_at=:now, updated_at=:now, file_size=:size",
                ConditionExpression="application_id=:app AND s3_key=:key AND #s=:waiting",
                ExpressionAttributeNames={"#s":"status"},
                ExpressionAttributeValues={":received":"Received",":now":now_iso(),":size":metadata["ContentLength"],
                    ":app":item["application_id"],":key":key,":waiting":"Waiting"},ReturnValues="ALL_NEW")
            item=result["Attributes"]
        except ClientError as exc:
            if exc.response.get("Error",{}).get("Code") == "ConditionalCheckFailedException":
                return response(409,{"message":"Document changed. Refresh and retry confirmation."})
            raise
    return response(200,{"document":{"document_id":document_id,"reference":application.get("reference",""),
        "name":item.get("name","Document"),"type":item.get("content_type","Document"),
        "status":item.get("status","Received"),"created_at":item.get("created_at","")}})


def lambda_handler(event, context):
    method, path = route_from_event(event)
    if method == "OPTIONS":
        return response(200, {"message": "CORS OK"})

    try:
        if method == "POST" and path.startswith("/documents/") and path.endswith("/complete"):
            return complete_document_upload(event, path.split("/")[2])
        if method == "GET" and path == "/documents":
            return list_client_documents(event)
        if method == "GET" and path.startswith("/documents/") and path.endswith("/download"):
            return document_download(event, path.split("/")[2])
        if method == "GET" and path == "/staff/overview":
            return staff_overview(event)
        if method == "PATCH" and path.startswith("/staff/tasks/"):
            return update_staff_task(event, path.rsplit("/", 1)[-1])
        if method == "GET" and path == "/admin/overview":
            return admin_overview(event)
        if method == "POST" and path == "/admin/tasks":
            return create_admin_task(event)
        if method == "PATCH" and path.startswith("/admin/tasks/"):
            return update_admin_task(event, path.rsplit("/", 1)[-1])
        if method == "POST" and path == "/auth/register":
            return register(body_from_event(event))
        if method == "POST" and path == "/auth/resend-confirmation":
            return resend_confirmation(body_from_event(event))
        if method == "POST" and path == "/auth/login":
            return login(body_from_event(event))
        if method == "POST" and path == "/auth/confirm":
            return confirm_registration(body_from_event(event))
        if method == "POST" and path == "/auth/forgot-password":
            return forgot_password(body_from_event(event))
        if method == "POST" and path == "/auth/confirm-forgot-password":
            return confirm_forgot_password(body_from_event(event))
        if method == "POST" and path in ("/applications", "/guest/applications"):
            return create_application(event)
        if method == "POST" and path == "/account/applications":
            return create_account_application(event)
        if method == "GET" and path == "/applications":
            return list_applications(event)

        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "applications":
            if method == "GET":
                return get_application(event, parts[1])
            if method == "PATCH":
                return update_application(event, parts[1])
        if len(parts) == 3 and parts[0] == "applications" and parts[2] == "documents" and method == "POST":
            return create_document_upload(event, parts[1])
        if len(parts) == 3 and parts[0] == "applications" and parts[2] == "messages" and method == "POST":
            return create_message(event, parts[1])
        if len(parts) == 3 and parts[0] == "applications" and parts[2] == "payments" and method == "POST":
            return create_payment(event, parts[1])
    except json.JSONDecodeError:
        return response(400, {"message": "Invalid JSON body"})
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")
        messages = {
            "NotAuthorizedException": (401, "Invalid credentials or code"),
            "UserNotFoundException": (401, "Invalid credentials or code"),
            "UserNotConfirmedException": (403, "Confirm your email before signing in"),
            "UsernameExistsException": (409, "Account exists. Sign in or confirm your email"),
            "CodeMismatchException": (400, "Incorrect confirmation code"),
            "ExpiredCodeException": (400, "Code expired. Request a new code"),
            "InvalidPasswordException": (400, "Password does not meet the required policy"),
            "InvalidParameterException": (400, "Check the supplied registration or authentication fields"),
            "TooManyRequestsException": (429, "Too many attempts. Try again later"),
            "LimitExceededException": (429, "Too many attempts. Try again later"),
        }
        status, message = messages.get(code, (503, "Service temporarily unavailable. Please retry"))
        return response(status, {"message": message, "code": code})
    except Exception as error:
        print("Unhandled error type", type(error).__name__)
        return response(500, {"message": "Internal server error"})

    return response(404, {"message": "Route not found"})
