terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

locals {
  states = toset([
    "Alabama", "Alaska", "Arizona", "Arkansas", "California",
    "Colorado", "Connecticut", "Delaware", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
    "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri",
    "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming"
  ])
}

resource "aws_s3_bucket" "forms" {
  bucket        = "4incorp.com-client-intake-forms"
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "forms" {
  bucket                  = aws_s3_bucket.forms.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "forms" {
  bucket = aws_s3_bucket.forms.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "forms" {
  bucket = aws_s3_bucket.forms.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "state_folder" {
  for_each = local.states
  bucket   = aws_s3_bucket.forms.id
  key      = "${each.value}/"
  content  = ""

  depends_on = [
    aws_s3_bucket_public_access_block.forms,
    aws_s3_bucket_ownership_controls.forms,
    aws_s3_bucket_server_side_encryption_configuration.forms
  ]
}

output "bucket_name" {
  value = aws_s3_bucket.forms.id
}

output "state_folders" {
  value = sort([for folder in aws_s3_object.state_folder : folder.key])
}

output "state_folder_count" {
  value = length(aws_s3_object.state_folder)
}
