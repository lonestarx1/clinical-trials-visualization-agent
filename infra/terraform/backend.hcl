# terraform init -backend-config=backend.hcl (bucket created by ./bootstrap)
bucket       = "cheiron-tfstate-370406301147"
key          = "cheiron/terraform.tfstate"
region       = "ap-northeast-2"
profile      = "personal"
use_lockfile = true
encrypt      = true
