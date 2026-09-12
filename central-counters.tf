# Reuse the existing table shown in the AWS console. Do not enable counters.tf.disabled.
data "aws_dynamodb_table" "central_counters" {
  name = "${var.fourincorp_stack_name}-counters"

  lifecycle {
    postcondition {
      condition     = self.hash_key == "counter_name" && (self.range_key == "" || self.range_key == null)
      error_message = "The existing counters table must have counter_name as its only primary key."
    }
  }
}

variable "fourincorp_central_counters_enabled" {
  type        = bool
  default     = false
  description = "Enable only after pausing API writes and refreshing the existing sequence values."
}

variable "fourincorp_counter_cutover_pause" {
  type        = bool
  default     = false
  description = "Temporarily reserve zero API concurrency during the counter migration."
}

locals {
  counter_specs = [
    { table = aws_dynamodb_table.fourincorp_clients.name, keys = ["user_id"], number_attribute = "client_id", start = 100, assign_missing = false, legacy_key = { user_id = "__CLIENT_COUNTER__" }, legacy_attribute = "last_client_id" },
    { table = aws_dynamodb_table.fourincorp_applications.name, keys = ["application_id"], number_attribute = "order_id", start = 100, assign_missing = false, legacy_key = { application_id = "__ORDER_COUNTER__" }, legacy_attribute = "order_id" },
    { table = aws_dynamodb_table.fourincorp_documents.name, keys = ["document_id"], number_attribute = "record_number", start = 0, assign_missing = true },
    { table = aws_dynamodb_table.fourincorp_payments.name, keys = ["payment_id"], number_attribute = "record_number", start = 0, assign_missing = true },
    { table = aws_dynamodb_table.fourincorp_messages.name, keys = ["message_id"], number_attribute = "record_number", start = 0, assign_missing = true },
    { table = aws_dynamodb_table.fourincorp_events.name, keys = ["application_id", "event_id"], number_attribute = "record_number", start = 0, assign_missing = true },
    { table = aws_dynamodb_table.fourincorp_cancellations.name, keys = ["cancellation_id"], number_attribute = "record_number", start = 0, assign_missing = true },
    { table = aws_dynamodb_table.staff_tasks.name, keys = ["task_id"], number_attribute = "record_number", start = 0, assign_missing = true }
  ]
  counter_source_arns = [
    aws_dynamodb_table.fourincorp_clients.arn,
    aws_dynamodb_table.fourincorp_applications.arn,
    aws_dynamodb_table.fourincorp_documents.arn,
    aws_dynamodb_table.fourincorp_payments.arn,
    aws_dynamodb_table.fourincorp_messages.arn,
    aws_dynamodb_table.fourincorp_events.arn,
    aws_dynamodb_table.fourincorp_cancellations.arn,
    aws_dynamodb_table.staff_tasks.arn
  ]
}

resource "aws_iam_role_policy" "central_counter_api" {
  name = "${var.fourincorp_stack_name}-central-counters"
  role = aws_iam_role.fourincorp_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:UpdateItem"]
      Resource = data.aws_dynamodb_table.central_counters.arn
    }]
  })
}

resource "aws_iam_role" "counter_sync" {
  name = "${var.fourincorp_stack_name}-counter-sync"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "counter_sync_logs" {
  role       = aws_iam_role.counter_sync.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "counter_sync" {
  name = "${var.fourincorp_stack_name}-counter-sync"
  role = aws_iam_role.counter_sync.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["dynamodb:Scan", "dynamodb:GetItem"], Resource = local.counter_source_arns },
      { Effect = "Allow", Action = ["dynamodb:UpdateItem"], Resource = [
        aws_dynamodb_table.fourincorp_documents.arn, aws_dynamodb_table.fourincorp_payments.arn,
        aws_dynamodb_table.fourincorp_messages.arn, aws_dynamodb_table.fourincorp_events.arn,
        aws_dynamodb_table.fourincorp_cancellations.arn, aws_dynamodb_table.staff_tasks.arn
      ] },
      { Effect = "Allow", Action = ["dynamodb:UpdateItem"], Resource = data.aws_dynamodb_table.central_counters.arn }
    ]
  })
}

data "archive_file" "counter_sync" {
  type        = "zip"
  source_file = "${path.module}/lambda/counter_sync.py"
  output_path = "${path.module}/counter_sync.zip"
}

resource "aws_lambda_function" "counter_sync" {
  function_name                  = "${var.fourincorp_stack_name}-counter-sync"
  filename                       = data.archive_file.counter_sync.output_path
  source_code_hash               = data.archive_file.counter_sync.output_base64sha256
  role                           = aws_iam_role.counter_sync.arn
  handler                        = "counter_sync.lambda_handler"
  runtime                        = "python3.12"
  timeout                        = 240
  memory_size                    = 512
  reserved_concurrent_executions = -1
  environment {
    variables = {
      COUNTERS_TABLE = data.aws_dynamodb_table.central_counters.name
      TABLE_SPECS    = jsonencode(local.counter_specs)
    }
  }
  depends_on = [aws_iam_role_policy.counter_sync, aws_iam_role_policy_attachment.counter_sync_logs]
}

resource "aws_cloudwatch_event_rule" "counter_sync" {
  name                = "${var.fourincorp_stack_name}-counter-sync"
  schedule_expression = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_target" "counter_sync" {
  rule = aws_cloudwatch_event_rule.counter_sync.name
  arn  = aws_lambda_function.counter_sync.arn
}

resource "aws_lambda_permission" "counter_sync_schedule" {
  statement_id  = "AllowCounterSchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.counter_sync.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.counter_sync.arn
}

resource "aws_cloudwatch_metric_alarm" "counter_sync_errors" {
  alarm_name          = "${var.fourincorp_stack_name}-counter-sync-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { FunctionName = aws_lambda_function.counter_sync.function_name }
}

output "central_counter_sync_function" {
  value = aws_lambda_function.counter_sync.function_name
}

output "central_counter_api_function" {
  value = aws_lambda_function.fourincorp_api.function_name
}

output "central_counter_table" {
  value = data.aws_dynamodb_table.central_counters.name
}

output "central_counter_allocation_enabled" {
  value = var.fourincorp_central_counters_enabled
}
