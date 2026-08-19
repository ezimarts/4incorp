locals {
  fourincorp_allowed_origin = var.fourincorp_allowed_origin != "" ? var.fourincorp_allowed_origin : "https://${var.fourincorp_domain_name}"
}

resource "aws_dynamodb_table" "fourincorp_users" {
  name         = "${var.fourincorp_stack_name}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "email"
    type = "S"
  }

  attribute {
    name = "phone"
    type = "S"
  }

  global_secondary_index {
    name            = "email-index"
    hash_key        = "email"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "phone-index"
    hash_key        = "phone"
    projection_type = "ALL"
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_dynamodb_table" "fourincorp_applications" {
  name         = "${var.fourincorp_stack_name}-applications"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "application_id"

  attribute {
    name = "application_id"
    type = "S"
  }

  attribute {
    name = "reference"
    type = "S"
  }

  attribute {
    name = "customer_email"
    type = "S"
  }

  attribute {
    name = "submitted_at"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "updated_at"
    type = "S"
  }

  attribute {
    name = "assigned_staff_email"
    type = "S"
  }

  global_secondary_index {
    name            = "reference-index"
    hash_key        = "reference"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "customer-email-submitted-index"
    hash_key        = "customer_email"
    range_key       = "submitted_at"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "status-updated-index"
    hash_key        = "status"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "assigned-staff-index"
    hash_key        = "assigned_staff_email"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_dynamodb_table" "fourincorp_documents" {
  name         = "${var.fourincorp_stack_name}-documents"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "document_id"

  attribute {
    name = "document_id"
    type = "S"
  }

  attribute {
    name = "application_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "application-created-index"
    hash_key        = "application_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_dynamodb_table" "fourincorp_payments" {
  name         = "${var.fourincorp_stack_name}-payments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "payment_id"

  attribute {
    name = "payment_id"
    type = "S"
  }

  attribute {
    name = "application_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "application-created-index"
    hash_key        = "application_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_dynamodb_table" "fourincorp_messages" {
  name         = "${var.fourincorp_stack_name}-messages"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "message_id"

  attribute {
    name = "message_id"
    type = "S"
  }

  attribute {
    name = "application_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "application-created-index"
    hash_key        = "application_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_dynamodb_table" "fourincorp_otps" {
  name         = "${var.fourincorp_stack_name}-otps"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "otp_id"

  attribute {
    name = "otp_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_s3_bucket" "fourincorp_documents" {
  bucket = var.fourincorp_documents_bucket_name

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_s3_bucket_public_access_block" "fourincorp_documents" {
  bucket                  = aws_s3_bucket.fourincorp_documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "fourincorp_documents" {
  bucket = aws_s3_bucket.fourincorp_documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "fourincorp_documents" {
  bucket = aws_s3_bucket.fourincorp_documents.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["POST", "PUT", "GET", "HEAD"]
    allowed_origins = [local.fourincorp_allowed_origin]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket" "fourincorp_frontend" {
  bucket = var.fourincorp_frontend_bucket_name

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_s3_bucket_public_access_block" "fourincorp_frontend" {
  bucket                  = aws_s3_bucket.fourincorp_frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "fourincorp_frontend" {
  name                              = "${var.fourincorp_stack_name}-frontend-oac"
  description                       = "CloudFront access to the private 4incorp frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "fourincorp_frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = "${var.fourincorp_stack_name} frontend"
  aliases             = var.fourincorp_acm_certificate_arn == "" ? [] : [var.fourincorp_domain_name, "www.${var.fourincorp_domain_name}"]

  origin {
    domain_name              = aws_s3_bucket.fourincorp_frontend.bucket_regional_domain_name
    origin_id                = "fourincorp-frontend-s3"
    origin_access_control_id = aws_cloudfront_origin_access_control.fourincorp_frontend.id
  }

  default_cache_behavior {
    target_origin_id       = "fourincorp-frontend-s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
  }

  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn            = var.fourincorp_acm_certificate_arn == "" ? null : var.fourincorp_acm_certificate_arn
    cloudfront_default_certificate = var.fourincorp_acm_certificate_arn == ""
    minimum_protocol_version       = var.fourincorp_acm_certificate_arn == "" ? null : "TLSv1.2_2021"
    ssl_support_method             = var.fourincorp_acm_certificate_arn == "" ? null : "sni-only"
  }
}

data "aws_iam_policy_document" "fourincorp_frontend_bucket" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.fourincorp_frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.fourincorp_frontend.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "fourincorp_frontend" {
  bucket = aws_s3_bucket.fourincorp_frontend.id
  policy = data.aws_iam_policy_document.fourincorp_frontend_bucket.json
}

data "archive_file" "fourincorp_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/fourincorp_lambda.py"
  output_path = "${path.module}/4incorp_lambda.zip"
}

resource "aws_iam_role" "fourincorp_lambda" {
  name = "${var.fourincorp_stack_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "fourincorp_lambda_logs" {
  role       = aws_iam_role.fourincorp_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "fourincorp_lambda" {
  name = "${var.fourincorp_stack_name}-lambda-policy"
  role = aws_iam_role.fourincorp_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.fourincorp_users.arn,
          "${aws_dynamodb_table.fourincorp_users.arn}/index/*",
          aws_dynamodb_table.fourincorp_applications.arn,
          "${aws_dynamodb_table.fourincorp_applications.arn}/index/*",
          aws_dynamodb_table.fourincorp_documents.arn,
          "${aws_dynamodb_table.fourincorp_documents.arn}/index/*",
          aws_dynamodb_table.fourincorp_payments.arn,
          "${aws_dynamodb_table.fourincorp_payments.arn}/index/*",
          aws_dynamodb_table.fourincorp_messages.arn,
          "${aws_dynamodb_table.fourincorp_messages.arn}/index/*",
          aws_dynamodb_table.fourincorp_otps.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.fourincorp_documents.arn}/*"
      }
    ]
  })
}

resource "aws_lambda_function" "fourincorp_api" {
  function_name    = "${var.fourincorp_stack_name}-api"
  filename         = data.archive_file.fourincorp_lambda_zip.output_path
  source_code_hash = data.archive_file.fourincorp_lambda_zip.output_base64sha256
  role             = aws_iam_role.fourincorp_lambda.arn
  handler          = "fourincorp_lambda.lambda_handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      USERS_TABLE        = aws_dynamodb_table.fourincorp_users.name
      APPLICATIONS_TABLE = aws_dynamodb_table.fourincorp_applications.name
      DOCUMENTS_TABLE    = aws_dynamodb_table.fourincorp_documents.name
      PAYMENTS_TABLE     = aws_dynamodb_table.fourincorp_payments.name
      MESSAGES_TABLE     = aws_dynamodb_table.fourincorp_messages.name
      OTPS_TABLE         = aws_dynamodb_table.fourincorp_otps.name
      DOCUMENT_BUCKET    = aws_s3_bucket.fourincorp_documents.id
      APP_SECRET         = var.fourincorp_app_secret
      ADMIN_EMAIL        = var.fourincorp_admin_email
      STAFF_EMAILS       = join(",", var.fourincorp_staff_emails)
      ALLOWED_ORIGIN     = local.fourincorp_allowed_origin
    }
  }
}

resource "aws_apigatewayv2_api" "fourincorp" {
  name          = "${var.fourincorp_stack_name}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_credentials = false
    allow_headers     = ["Authorization", "Content-Type"]
    allow_methods     = ["OPTIONS", "GET", "POST", "PATCH", "DELETE"]
    allow_origins     = [local.fourincorp_allowed_origin]
    max_age           = 300
  }
}

resource "aws_apigatewayv2_integration" "fourincorp_lambda" {
  api_id                 = aws_apigatewayv2_api.fourincorp.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.fourincorp_api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "fourincorp_proxy" {
  api_id    = aws_apigatewayv2_api.fourincorp.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.fourincorp_lambda.id}"
}

resource "aws_apigatewayv2_route" "fourincorp_root" {
  api_id    = aws_apigatewayv2_api.fourincorp.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.fourincorp_lambda.id}"
}

resource "aws_apigatewayv2_stage" "fourincorp_prod" {
  api_id      = aws_apigatewayv2_api.fourincorp.id
  name        = "prod"
  auto_deploy = true
}

resource "aws_lambda_permission" "fourincorp_api_gateway" {
  statement_id  = "Allow4incorpAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fourincorp_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.fourincorp.execution_arn}/*/*"
}
