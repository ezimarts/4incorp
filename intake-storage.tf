# Add to the MAIN backend project, not the separate bucket project.
# The existing intake bucket remains managed by its original Terraform state.
data "aws_s3_bucket" "intake_existing" {
  bucket = "4incorp.com-client-intake-forms"
}

resource "aws_iam_role_policy" "intake_storage" {
  name = "${var.fourincorp_stack_name}-intake-storage"
  role = aws_iam_role.fourincorp_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:GetObject"]
      Resource = "${data.aws_s3_bucket.intake_existing.arn}/*"
    }]
  })
}

resource "aws_s3_bucket_cors_configuration" "intake_storage" {
  bucket = data.aws_s3_bucket.intake_existing.id
  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["POST", "GET", "HEAD"]
    allowed_origins = [local.fourincorp_allowed_origin]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}
