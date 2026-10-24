output "region" {
  value = var.region
}

output "instance_id" {
  value = aws_instance.node.id
}

output "public_ip" {
  value = aws_eip.node.public_ip
}

output "registry" {
  value = local.registry
}

output "secret_name" {
  value = aws_secretsmanager_secret.openai.name
}

output "app_url" {
  value = "https://${var.app_host}"
}

output "api_url" {
  value = "https://${var.api_host}"
}
