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
  default     = "4incorp.com"
}

variable "fourincorp_documents_bucket_name" {
  description = "Private S3 bucket that stores uploaded application documents"
  type        = string
  default     = "4incorp-application-documents"
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

variable "fourincorp_stripe_secret_name" {
  description = "Secrets Manager name for the 4incorp Stripe API and webhook credentials"
  type        = string
  default     = "4incorp/stripe"
}

variable "fourincorp_stripe_success_url" {
  description = "Browser URL Stripe redirects to after a successful Checkout session"
  type        = string
  default     = "https://4incorp.com/?payment=success"
}

variable "fourincorp_stripe_cancel_url" {
  description = "Browser URL Stripe redirects to when Checkout is cancelled"
  type        = string
  default     = "https://4incorp.com/?payment=cancelled"
}
