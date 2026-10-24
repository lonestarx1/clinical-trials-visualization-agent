resource "aws_ecr_repository" "app" {
  for_each             = toset(["api", "web"])
  name                 = "${var.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE" # tags are git commits
  force_delete         = true        # so `terraform destroy` leaves nothing billable
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  for_each   = aws_ecr_repository.app
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

# The value is set outside Terraform (see infra/README.md), so it never lands in state.
resource "aws_secretsmanager_secret" "openai" {
  name                    = "${var.name}/openai-api-key"
  description             = "OpenAI API key for the cheiron API"
  recovery_window_in_days = 0
}
