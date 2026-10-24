terraform {
  required_version = ">= 1.10" # S3 backend with native locking (use_lockfile)
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.80" }
  }
  backend "s3" {} # settings in backend.hcl
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile
  default_tags {
    tags = { Project = "cheiron-ctviz", ManagedBy = "terraform" }
  }
}
