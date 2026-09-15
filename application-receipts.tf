# SES identity and DNS authentication for automatic customer application receipts.
resource "aws_ses_domain_identity" "fourincorp" {
  domain = var.fourincorp_domain_name
}

resource "aws_route53_record" "fourincorp_ses_verification" {
  zone_id         = local.fourincorp_zone_id
  name            = "_amazonses.${var.fourincorp_domain_name}"
  type            = "TXT"
  ttl             = 600
  records         = [aws_ses_domain_identity.fourincorp.verification_token]
  allow_overwrite = true
}

resource "aws_ses_domain_identity_verification" "fourincorp" {
  domain     = aws_ses_domain_identity.fourincorp.id
  depends_on = [aws_route53_record.fourincorp_ses_verification]
}

resource "aws_ses_domain_dkim" "fourincorp" {
  domain = aws_ses_domain_identity.fourincorp.domain
}

# Stop future receipt emails to addresses that hard-bounce or register a
# complaint. This is the account-level bounce/complaint handling process
# declared in the SES production-access request.
resource "aws_sesv2_account_suppression_attributes" "receipts" {
  suppressed_reasons = ["BOUNCE", "COMPLAINT"]
}

resource "aws_route53_record" "fourincorp_ses_dkim" {
  for_each = {
    first  = 0
    second = 1
    third  = 2
  }

  zone_id         = local.fourincorp_zone_id
  name            = "${aws_ses_domain_dkim.fourincorp.dkim_tokens[each.value]}._domainkey.${var.fourincorp_domain_name}"
  type            = "CNAME"
  ttl             = 600
  records         = ["${aws_ses_domain_dkim.fourincorp.dkim_tokens[each.value]}.dkim.amazonses.com"]
  allow_overwrite = true
}
