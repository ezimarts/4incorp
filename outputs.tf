output "fourincorp_api_url" {
  value = aws_apigatewayv2_stage.fourincorp_prod.invoke_url
}

output "fourincorp_frontend_cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.fourincorp_frontend.domain_name}"
}

output "fourincorp_cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.fourincorp_frontend.id
}

output "fourincorp_frontend_bucket_name" {
  value = aws_s3_bucket.fourincorp_frontend.id
}

output "fourincorp_documents_bucket_name" {
  value = aws_s3_bucket.fourincorp_documents.id
}

output "fourincorp_client_records_bucket_name" {
  value = aws_s3_bucket.fourincorp_client_records.id
}

output "fourincorp_applications_table_name" {
  value = aws_dynamodb_table.fourincorp_applications.name
}

output "fourincorp_clients_table_name" {
  value = aws_dynamodb_table.fourincorp_clients.name
}

output "fourincorp_domain" {
  value = "https://${var.fourincorp_domain_name}"
}

output "fourincorp_certificate_arn" {
  value = aws_acm_certificate.fourincorp.arn
}

output "fourincorp_cognito_user_pool_id" {
  value = aws_cognito_user_pool.fourincorp.id
}

output "fourincorp_cognito_client_id" {
  value = aws_cognito_user_pool_client.fourincorp_web.id
}

output "fourincorp_stripe_secret_arn" {
  value = aws_secretsmanager_secret.fourincorp_stripe.arn
}

output "fourincorp_stripe_webhook_url" {
  value = "${aws_apigatewayv2_stage.fourincorp_prod.invoke_url}/payments/webhook"
}
