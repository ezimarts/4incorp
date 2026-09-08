# Add to the MAIN 4incorp Terraform project. Reuses its Cognito pool,
# clients table, Lambda, API Gateway and CloudFront/S3 website.
resource "aws_s3_object" "registration_config" {
  bucket        = aws_s3_bucket.fourincorp_frontend.id
  key           = "config.js"
  content_type  = "application/javascript"
  cache_control = "no-cache, max-age=0, must-revalidate"
  content = "window.FOURINCORP_CONFIG = ${jsonencode({
    apiBaseUrl        = aws_apigatewayv2_stage.fourincorp_prod.invoke_url
    cognitoUserPoolId = aws_cognito_user_pool.fourincorp.id
    cognitoClientId   = aws_cognito_user_pool_client.fourincorp_web.id
  })};"
}

resource "aws_s3_object" "registration_frontend" {
  for_each = {
    "index.html"        = { source = "4incorpindex.html", type = "text/html" }
    "production-api.js" = { source = "production-api.js", type = "application/javascript" }
  }
  bucket        = aws_s3_bucket.fourincorp_frontend.id
  key           = each.key
  source        = "${path.module}/${each.value.source}"
  source_hash   = filesha256("${path.module}/${each.value.source}")
  content_type  = each.value.type
  cache_control = "no-cache, max-age=0, must-revalidate"
  depends_on    = [aws_s3_object.registration_config, aws_lambda_function.fourincorp_api]
}

output "registration_cloudfront_id" {
  value = aws_cloudfront_distribution.fourincorp_frontend.id
}
