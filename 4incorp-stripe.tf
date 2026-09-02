resource "aws_dynamodb_table" "fourincorp_events" {
  name         = "${var.fourincorp_stack_name}-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "application_id"
  range_key    = "event_id"

  attribute {
    name = "application_id"
    type = "S"
  }

  attribute {
    name = "event_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_dynamodb_table" "fourincorp_cancellations" {
  name         = "${var.fourincorp_stack_name}-cancellations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "cancellation_id"

  attribute {
    name = "cancellation_id"
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

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_secretsmanager_secret" "fourincorp_stripe" {
  name                    = var.fourincorp_stripe_secret_name
  description             = "Stripe API and webhook secrets for 4incorp"
  recovery_window_in_days = 7

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

data "archive_file" "fourincorp_stripe_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/stripe_lambda.py"
  output_path = "${path.module}/4incorp_stripe_lambda.zip"
}

resource "aws_iam_role" "fourincorp_stripe_lambda" {
  name = "${var.fourincorp_stack_name}-stripe-lambda-role"

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

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_iam_role_policy_attachment" "fourincorp_stripe_logs" {
  role       = aws_iam_role.fourincorp_stripe_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "fourincorp_stripe" {
  name = "${var.fourincorp_stack_name}-stripe-policy"
  role = aws_iam_role.fourincorp_stripe_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.fourincorp_stripe.arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.fourincorp_applications.arn,
          "${aws_dynamodb_table.fourincorp_applications.arn}/index/*",
          aws_dynamodb_table.fourincorp_payments.arn,
          "${aws_dynamodb_table.fourincorp_payments.arn}/index/*",
          aws_dynamodb_table.fourincorp_events.arn
        ]
      }
    ]
  })
}

resource "aws_lambda_function" "fourincorp_stripe" {
  function_name    = "${var.fourincorp_stack_name}-stripe"
  filename         = data.archive_file.fourincorp_stripe_lambda_zip.output_path
  source_code_hash = data.archive_file.fourincorp_stripe_lambda_zip.output_base64sha256
  role             = aws_iam_role.fourincorp_stripe_lambda.arn
  handler          = "stripe_lambda.lambda_handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      APPLICATIONS_TABLE = aws_dynamodb_table.fourincorp_applications.name
      PAYMENTS_TABLE     = aws_dynamodb_table.fourincorp_payments.name
      EVENTS_TABLE       = aws_dynamodb_table.fourincorp_events.name
      STRIPE_SECRET_ARN  = aws_secretsmanager_secret.fourincorp_stripe.arn
      STRIPE_SUCCESS_URL = var.fourincorp_stripe_success_url
      STRIPE_CANCEL_URL  = var.fourincorp_stripe_cancel_url
      ALLOWED_ORIGIN     = local.fourincorp_allowed_origin
    }
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_apigatewayv2_integration" "fourincorp_stripe" {
  api_id                 = aws_apigatewayv2_api.fourincorp.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.fourincorp_stripe.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "fourincorp_stripe_checkout" {
  api_id    = aws_apigatewayv2_api.fourincorp.id
  route_key = "POST /payments/checkout"
  target    = "integrations/${aws_apigatewayv2_integration.fourincorp_stripe.id}"
}

resource "aws_apigatewayv2_route" "fourincorp_stripe_webhook" {
  api_id    = aws_apigatewayv2_api.fourincorp.id
  route_key = "POST /payments/webhook"
  target    = "integrations/${aws_apigatewayv2_integration.fourincorp_stripe.id}"
}

resource "aws_lambda_permission" "fourincorp_stripe_api_gateway" {
  statement_id  = "Allow4incorpStripeAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fourincorp_stripe.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.fourincorp.execution_arn}/*/POST/payments/*"
}
