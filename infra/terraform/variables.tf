variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "aws_profile" {
  type    = string
  default = "personal"
}

variable "name" {
  type    = string
  default = "cheiron"
}

variable "instance_type" {
  description = "One node runs k3s, the API, the web app and Postgres. The largest question needs ~2 GB, so 8 GB (t3.large) leaves headroom; t3.medium (4 GB) is tight."
  type        = string
  default     = "t3.large"
}

variable "use_spot" {
  description = "Spot is ~70% cheaper; AWS may reclaim the node with 2 minutes' notice."
  type        = bool
  default     = false
}

variable "zone_name" {
  type    = string
  default = "engineeradriel.com"
}

variable "app_host" {
  type    = string
  default = "trials.cheiron.engineeradriel.com"
}

variable "api_host" {
  type    = string
  default = "api.cheiron.engineeradriel.com"
}

variable "k3s_version" {
  type    = string
  default = "v1.33.5+k3s1"
}

variable "cert_manager_version" {
  type    = string
  default = "v1.19.4"
}
