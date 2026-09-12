# Add to the MAIN project. The existing registration_frontend resource
# continues to deploy 4incorpindex.html as the public index.html.
resource "aws_s3_object" "team_portals" {
  for_each = {
    "admin.html"      = "text/html"
    "staff.html"      = "text/html"
    "team-portal.js"  = "application/javascript"
    "team-portal.css" = "text/css"
  }
  bucket        = aws_s3_bucket.fourincorp_frontend.id
  key           = each.key
  source        = "${path.module}/${each.key}"
  source_hash   = filesha256("${path.module}/${each.key}")
  content_type  = each.value
  cache_control = "no-cache, max-age=0, must-revalidate"
}
