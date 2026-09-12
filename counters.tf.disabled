# Add to the main 4incorp Terraform project.
# Counter items are managed by the backend, not by Terraform.
resource "aws_dynamodb_table" "fourincorp_counters" {
  name         = "${var.fourincorp_stack_name}-counters"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "counter_name"

  attribute {
    name = "counter_name"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Application = "4incorp"
    Environment = var.fourincorp_environment
  }
}

output "fourincorp_counters_table_name" {
  value = aws_dynamodb_table.fourincorp_counters.name
}
