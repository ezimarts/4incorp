terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }

    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}
provider "aws" {
  region              = var.aws_region
  profile             = "4incorp"
  allowed_account_ids = ["424123860784"]
}