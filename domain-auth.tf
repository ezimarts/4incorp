data "aws_route53_zone" "fourincorp" {
  count        = var.fourincorp_route53_zone_id == "" ? 1 : 0
  name         = "${var.fourincorp_domain_name}."
  private_zone = false
}

locals {
  fourincorp_zone_id = var.fourincorp_route53_zone_id != "" ? var.fourincorp_route53_zone_id : data.aws_route53_zone.fourincorp[0].zone_id
}

resource "aws_acm_certificate" "fourincorp" {
  domain_name               = var.fourincorp_domain_name
  subject_alternative_names = ["www.${var.fourincorp_domain_name}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_route53_record" "fourincorp_certificate_validation" {
  for_each = {
    for option in aws_acm_certificate.fourincorp.domain_validation_options : option.domain_name => {
      name   = option.resource_record_name
      record = option.resource_record_value
      type   = option.resource_record_type
    }
  }

  allow_overwrite = true
  zone_id         = local.fourincorp_zone_id
  name            = each.value.name
  type            = each.value.type
  ttl             = 300
  records         = [each.value.record]
}

resource "aws_acm_certificate_validation" "fourincorp" {
  certificate_arn         = aws_acm_certificate.fourincorp.arn
  validation_record_fqdns = [for record in aws_route53_record.fourincorp_certificate_validation : record.fqdn]
}

resource "aws_route53_record" "fourincorp_apex_a" {
  zone_id = local.fourincorp_zone_id
  name    = var.fourincorp_domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.fourincorp_frontend.domain_name
    zone_id                = aws_cloudfront_distribution.fourincorp_frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "fourincorp_apex_aaaa" {
  zone_id = local.fourincorp_zone_id
  name    = var.fourincorp_domain_name
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.fourincorp_frontend.domain_name
    zone_id                = aws_cloudfront_distribution.fourincorp_frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "fourincorp_www_a" {
  zone_id = local.fourincorp_zone_id
  name    = "www.${var.fourincorp_domain_name}"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.fourincorp_frontend.domain_name
    zone_id                = aws_cloudfront_distribution.fourincorp_frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "fourincorp_www_aaaa" {
  zone_id = local.fourincorp_zone_id
  name    = "www.${var.fourincorp_domain_name}"
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.fourincorp_frontend.domain_name
    zone_id                = aws_cloudfront_distribution.fourincorp_frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_cognito_user_pool" "fourincorp" {
  name                     = "${var.fourincorp_stack_name}-${var.fourincorp_environment}-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  schema {
    attribute_data_type = "String"
    mutable             = true
    name                = "phone"
    required            = false
  }

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  lifecycle {
    # Cognito schema attributes cannot be modified or removed after pool
    # creation. The AWS provider may also return computed schema entries that
    # are absent from configuration, causing an invalid update request.
    ignore_changes = [schema]
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

resource "aws_cognito_user_pool_client" "fourincorp_web" {
  name         = "${var.fourincorp_stack_name}-web"
  user_pool_id = aws_cognito_user_pool.fourincorp.id

  generate_secret               = false
  prevent_user_existence_errors = "ENABLED"
  supported_identity_providers  = ["COGNITO"]
  explicit_auth_flows           = ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  access_token_validity         = 1
  id_token_validity             = 1
  refresh_token_validity        = 30
  enable_token_revocation       = true
}

resource "aws_cognito_user_group" "customer" {
  name         = "Customer"
  user_pool_id = aws_cognito_user_pool.fourincorp.id
  precedence   = 30
}

resource "aws_cognito_user_group" "staff" {
  name         = "Staff"
  user_pool_id = aws_cognito_user_pool.fourincorp.id
  precedence   = 20
}

resource "aws_cognito_user_group" "admin" {
  name         = "Admin"
  user_pool_id = aws_cognito_user_pool.fourincorp.id
  precedence   = 10
}

resource "aws_apigatewayv2_authorizer" "fourincorp_cognito" {
  api_id           = aws_apigatewayv2_api.fourincorp.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "4incorp-cognito"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.fourincorp_web.id]
    issuer   = "https://${aws_cognito_user_pool.fourincorp.endpoint}"
  }
}
