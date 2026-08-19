import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key


dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

USERS_TABLE = dynamodb.Table(os.environ["USERS_TABLE"])
APPLICATIONS_TABLE = dynamodb.Table(os.environ["APPLICATIONS_TABLE"])
DOCUMENTS_TABLE = dynamodb.Table(os.environ["DOCUMENTS_TABLE"])
PAYMENTS_TABLE = dynamodb.Table(os.environ["PAYMENTS_TABLE"])
MESSAGES_TABLE = dynamodb.Table(os.environ["MESSAGES_TABLE"])
OTPS_TABLE = dynamodb.Table(os.environ["OTPS_TABLE"])

DOCUMENT_BUCKET = os.environ["DOCUMENT_BUCKET"]
APP_SECRET = os.environ["APP_SECRET"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@4incorp.com").lower()
STAFF_EMAILS = {
    email.strip().lower()
    for email in os.environ.get("STAFF_EMAILS", "").split(",")
    if email.strip()
}
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")


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
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    authorization = headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected = hmac.new(
            APP_SECRET.encode("utf-8"),
            encoded_payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        supplied = b64url_decode(encoded_signature)
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(b64url_decode(encoded_payload))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def require_actor(event, roles=None):
    actor = actor_from_event(event)
    if not actor:
        return None, response(401, {"message": "Sign in required"})
    if roles and actor.get("role") not in roles:
        return None, response(403, {"message": "You do not have access"})
    return actor, None


def user_by_email(email):
    result = USERS_TABLE.query(
        IndexName="email-index",
        KeyConditionExpression=Key("email").eq(email.lower()),
        Limit=1,
    )
    items = result.get("Items", [])
    return items[0] if items else None


def public_user(user):
    return {
        "user_id": user["user_id"],
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
    if len(password) < 8:
        return response(400, {"message": "Password must be at least 8 characters"})
    if user_by_email(email):
        return response(409, {"message": "An account with this email already exists"})

    role = "admin" if email == ADMIN_EMAIL else "staff" if email in STAFF_EMAILS else "customer"
    user = {
        "user_id": str(uuid.uuid4()),
        "email": email,
        "phone": phone,
        "first_name": first_name,
        "last_name": last_name,
        "name": " ".join([first_name, last_name]).strip(),
        "role": role,
        "status": "active",
        "password_hash": hash_password(password),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    USERS_TABLE.put_item(Item=user)
    return response(201, {"user": public_user(user), "token": token_for(user)})


def login(body):
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    user = user_by_email(email)
    if not user or not verify_password(password, user.get("password_hash", "")):
        return response(401, {"message": "Invalid email or password"})
    if user.get("status") not in {"active", "Active"}:
        return response(403, {"message": "Account is not active"})
    return response(200, {"user": public_user(user), "token": token_for(user)})


def application_reference():
    return "4INC-" + datetime.now(timezone.utc).strftime("%y%m%d") + secrets.token_hex(2).upper()


def application_from_body(body, actor=None):
    customer_email = str(body.get("customerEmail") or body.get("customer_email") or body.get("email") or "").strip().lower()
    first_name = str(body.get("firstName") or body.get("first_name") or "").strip()
    last_name = str(body.get("lastName") or body.get("last_name") or "").strip()
    preferred_name = str(body.get("preferredName") or body.get("preferred_name") or "").strip()
    formation_state = str(body.get("formationState") or body.get("formation_state") or "").strip()
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
    return {
        "application_id": application_id,
        "reference": application_reference(),
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
        "raw": body,
        "status": "Submitted",
        "assigned_staff_email": "unassigned",
        "submitted_at": now,
        "updated_at": now,
    }


def create_application(event):
    actor = actor_from_event(event)
    body = body_from_event(event)
    try:
        application = application_from_body(body, actor)
    except ValueError as error:
        return response(400, {"message": str(error)})
    APPLICATIONS_TABLE.put_item(Item=application)
    return response(201, {"application": application, "reference": application["reference"]})


def list_applications(event):
    actor, error = require_actor(event)
    if error:
        return error
    if actor["role"] == "admin":
        items = APPLICATIONS_TABLE.scan().get("Items", [])
    elif actor["role"] == "staff":
        assigned = APPLICATIONS_TABLE.query(
            IndexName="assigned-staff-index",
            KeyConditionExpression=Key("assigned_staff_email").eq(actor["email"]),
        ).get("Items", [])
        unassigned = APPLICATIONS_TABLE.query(
            IndexName="assigned-staff-index",
            KeyConditionExpression=Key("assigned_staff_email").eq("unassigned"),
        ).get("Items", [])
        items = assigned + unassigned
    else:
        items = APPLICATIONS_TABLE.query(
            IndexName="customer-email-submitted-index",
            KeyConditionExpression=Key("customer_email").eq(actor["email"]),
        ).get("Items", [])
    items.sort(key=lambda item: item.get("submitted_at", ""), reverse=True)
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
    body = body_from_event(event)
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
    return response(200, {"application": result["Attributes"]})


def create_document_upload(event, reference):
    actor, error = require_actor(event)
    if error:
        return error
    application = get_application_by_reference(reference)
    if not application:
        return response(404, {"message": "Application not found"})
    if actor["role"] == "customer" and application.get("customer_email") != actor["email"]:
        return response(403, {"message": "You cannot add documents to this application"})

    body = body_from_event(event)
    file_name = str(body.get("file_name") or body.get("name") or "document").strip()
    content_type = str(body.get("content_type") or "application/octet-stream").strip()
    document_id = str(uuid.uuid4())
    key = f"applications/{application['application_id']}/documents/{document_id}/{file_name}"
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
        "reference": reference,
        "name": file_name,
        "content_type": content_type,
        "s3_key": key,
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
    return response(201, {"message": item})


def create_payment(event, reference):
    actor, error = require_actor(event, {"admin", "staff"})
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


def lambda_handler(event, context):
    method, path = route_from_event(event)
    if method == "OPTIONS":
        return response(200, {"message": "CORS OK"})

    try:
        if method == "POST" and path == "/auth/register":
            return register(body_from_event(event))
        if method == "POST" and path == "/auth/login":
            return login(body_from_event(event))
        if method == "POST" and path == "/applications":
            return create_application(event)
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
    except Exception as error:
        print("Unhandled error", repr(error))
        return response(500, {"message": "Internal server error"})

    return response(404, {"message": "Route not found"})
