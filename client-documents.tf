resource "aws_apigatewayv2_route" "client_documents" {
  for_each           = toset(["GET /documents", "GET /documents/{document_id}/download"])
  api_id             = aws_apigatewayv2_api.fourincorp.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.fourincorp_lambda.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.fourincorp_cognito.id
}

# Storage is private; the authenticated API resolves ownership through DynamoDB
# and signs a short-lived download URL. The existing Lambda archive and frontend
# source_hash resources deploy the client-document implementation.
output "client_document_storage" {
  description = "Client document storage and authenticated API endpoints"
  value = {
    bucket         = aws_s3_bucket.fourincorp_documents.id
    table          = aws_dynamodb_table.fourincorp_documents.name
    object_key     = "<client-id>/<client-name>/<document-id>/<filename>"
    list_url       = "${aws_apigatewayv2_stage.fourincorp_prod.invoke_url}/documents"
    download_route = "GET /documents/{document_id}/download"
  }
}
