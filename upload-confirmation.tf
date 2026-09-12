resource "aws_apigatewayv2_route" "document_upload_complete" {
  api_id             = aws_apigatewayv2_api.fourincorp.id
  route_key          = "POST /documents/{document_id}/complete"
  target             = "integrations/${aws_apigatewayv2_integration.fourincorp_lambda.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.fourincorp_cognito.id
}
