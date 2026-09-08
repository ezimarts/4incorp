variable "aws_region" {
  description = "AWS region for the 4incorp backend"
  type        = string
  default     = "us-east-1"
}

variable "fourincorp_stack_name" {
  description = "Name prefix for the 4incorp backend resources"
  type        = string
  default     = "4incorp"
}

variable "fourincorp_environment" {
  description = "Environment tag for the 4incorp stack"
  type        = string
  default     = "prod"
}

variable "fourincorp_domain_name" {
  description = "Primary frontend domain for 4incorp"
  type        = string
  default     = "4incorp.com"
}

variable "fourincorp_allowed_origin" {
  description = "Allowed browser origin for the 4incorp API and document uploads. Leave blank to use https://fourincorp_domain_name."
  type        = string
  default     = ""
}

variable "fourincorp_frontend_bucket_name" {
  description = "Private S3 bucket that stores the 4incorp frontend files"
  type        = string
  default     = "4incorp.com-web"
}

variable "fourincorp_documents_bucket_name" {
  description = "Private S3 bucket that stores uploaded application documents"
  type        = string
  default     = "4incorp.com-documents"
}

variable "fourincorp_client_records_bucket_name" {
  description = "Private S3 bucket for client form snapshots and client documents"
  type        = string
  default     = "clients-doc-record-4incorp"
}

variable "fourincorp_route53_zone_id" {
  description = "Optional Route 53 hosted-zone ID. Leave blank to discover the public 4incorp.com zone."
  type        = string
  default     = "Z04287301AJOFEKLBJ63Z"
}

variable "fourincorp_stripe_secret_name" {
  description = "Secrets Manager name containing StripeSecretKey and StripeWebhookSecret JSON keys"
  type        = string
  default     = "4incorp/prod/stripe"
}

variable "fourincorp_stripe_success_url" {
  description = "Stripe Checkout success redirect"
  type        = string
  default     = "https://4incorp.com/?payment=success&session_id={CHECKOUT_SESSION_ID}"
}

variable "fourincorp_stripe_cancel_url" {
  description = "Stripe Checkout cancellation redirect"
  type        = string
  default     = "https://4incorp.com/?payment=cancelled"
}

variable "fourincorp_acm_certificate_arn" {
  description = "Optional us-east-1 ACM certificate ARN for CloudFront aliases 4incorp.com and www.4incorp.com"
  type        = string
  default     = ""
}

variable "fourincorp_app_secret" {
  description = "HMAC secret used to sign 4incorp session tokens. Override this in terraform.tfvars for production."
  type        = string
  sensitive   = true
  default     = "replace-this-4incorp-session-secret-before-production"
}

variable "fourincorp_admin_email" {
  description = "Email address that receives admin role on registration"
  type        = string
  default     = "admin@4incorp.com"
}

variable "fourincorp_staff_emails" {
  description = "Email addresses that receive staff role on registration"
  type        = list(string)
  default     = []
}




