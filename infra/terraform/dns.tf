data "aws_route53_zone" "main" {
  name         = var.zone_name
  private_zone = false
}

resource "aws_route53_record" "host" {
  for_each = toset([var.app_host, var.api_host])
  zone_id  = data.aws_route53_zone.main.zone_id
  name     = each.key
  type     = "A"
  ttl      = 300
  records  = [aws_eip.node.public_ip]
}
