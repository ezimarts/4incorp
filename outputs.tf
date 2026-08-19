output "fourincorp_api_url" {
  value = aws_apigatewayv2_stage.fourincorp_prod.invoke_url
}

output "fourincorp_frontend_cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.fourincorp_frontend.domain_name}"
}

output "fourincorp_frontend_bucket_name" {
  value = aws_s3_bucket.fourincorp_frontend.id
}

output "fourincorp_documents_bucket_name" {
  value = aws_s3_bucket.fourincorp_documents.id
}

output "fourincorp_applications_table_name" {
  value = aws_dynamodb_table.fourincorp_applications.name
}

output "fourincorp_users_table_name" {
  value = aws_dynamodb_table.fourincorp_users.name
}
