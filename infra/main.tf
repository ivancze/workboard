# Workboard on Google Cloud. One flat configuration, applied by the operator
# from this directory; see README.md.

terraform {
  required_version = ">= 1.11" # write-only arguments

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
    # Firebase Hosting's resources exist only in the beta provider.
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 7.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }

  # Created by hand before the first init, since Terraform can't keep its state
  # in a bucket it creates.
  backend "gcs" {
    bucket = "prj-app-workboard-tfstate"
    prefix = "workboard"
  }
}

locals {
  project = "prj-app-workboard"
  region  = "asia-southeast1"
}

provider "google" {
  project = local.project
  region  = local.region

  # Signed in as a person rather than a service account, some APIs (budgets
  # among them) refuse a call that doesn't name a project to bill it to.
  user_project_override = true
  billing_project       = local.project
}

provider "google-beta" {
  project               = local.project
  region                = local.region
  user_project_override = true
  billing_project       = local.project
}
