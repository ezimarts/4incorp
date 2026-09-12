resource "aws_iam_role_policy" "staff_task_reads" {
  role = aws_iam_role.fourincorp_lambda.id
  name = "${var.fourincorp_stack_name}-staff-task-reads"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["dynamodb:Query"], Resource = "${aws_dynamodb_table.staff_tasks.arn}/index/staff-id-index" },
      { Effect = "Allow", Action = ["dynamodb:GetItem"], Resource = aws_dynamodb_table.staff_tasks.arn }
    ]
  })
}

resource "aws_apigatewayv2_route" "staff_tasks" {
  for_each           = toset(["GET /staff/overview", "PATCH /staff/tasks/{task_id}"])
  api_id             = aws_apigatewayv2_api.fourincorp.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.fourincorp_lambda.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.fourincorp_cognito.id
}

resource "aws_s3_object" "staff_progress_script" {
  bucket        = aws_s3_bucket.fourincorp_frontend.id
  key           = "staff-progress.js"
  source        = "${path.module}/staff-progress.js"
  source_hash   = filesha256("${path.module}/staff-progress.js")
  content_type  = "application/javascript"
  cache_control = "no-cache, max-age=0, must-revalidate"
}
