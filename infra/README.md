# Infrastructure

Workboard's Google Cloud setup, in the `prj-app-workboard` project, region
`asia-southeast1`. Why it looks like this: [ADR 0004](../docs/adr/0004-cloud-run-and-cloud-sql-behind-firebase.md).

One flat configuration. The operator runs every command here; nothing applies
it automatically. State lives in the `prj-app-workboard-tfstate` bucket, never
in the repository.

## From a fresh Mac to a working `terraform plan`

Run these from the repository root unless a step says otherwise.

### 1. Tools

```
brew install --cask gcloud-cli
brew install hashicorp/tap/terraform
gcloud --version && terraform -version
```

### 2. Sign in

Two sign-ins: one for `gcloud` itself, and one that Terraform uses
("application default credentials"). Each opens a browser.

```
gcloud auth login
gcloud projects list
```

The list must include `prj-app-workboard` in the `PROJECT_ID` column. If the
ID is different, stop: `infra/main.tf` names the project by its ID.

```
gcloud config set project prj-app-workboard
gcloud config set compute/region asia-southeast1
gcloud auth application-default login
gcloud auth application-default set-quota-project prj-app-workboard
```

### 3. The billing account

The budget needs the billing account's ID, and must be set in the account's
currency, which is Malaysian ringgit. If `gcloud` offers to enable an API
along the way, answer yes.

```
gcloud billing projects describe prj-app-workboard
```

`billingEnabled` must be `true`. `billingAccountName` is
`billingAccounts/<ID>`. Then check the currency:

```
gcloud billing accounts describe <ID>
```

If `currencyCode` isn't `MYR`, change `currency_code` and `units` in
`infra/budget.tf` to about $15 in that currency.

Save the ID where Terraform reads it. The file is ignored by git, which keeps
the ID out of the public repository:

```
echo 'billing_account = "<ID>"' > infra/terraform.tfvars
```

### 4. The state bucket

Terraform can't keep its state in a bucket it creates, so this one is made by
hand. Versioning keeps every earlier state, so a bad write can be undone.
Terraform also needs the Cloud Resource Manager API before it can enable any
other API, so that one is switched on here too.

```
gcloud services enable serviceusage.googleapis.com storage.googleapis.com \
  cloudresourcemanager.googleapis.com
gcloud storage buckets create gs://prj-app-workboard-tfstate \
  --location=asia-southeast1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://prj-app-workboard-tfstate --versioning
gcloud storage buckets describe gs://prj-app-workboard-tfstate \
  --format="yaml(location,versioning_enabled,uniform_bucket_level_access,public_access_prevention)"
```

Expect `ASIA-SOUTHEAST1`, versioning `true`, uniform access `true` and public
access prevention `enforced`.

### 5. Terraform

```
cd infra
terraform init
terraform plan
```

The first plan adds 15 resources: 14 APIs and the budget. Then:

```
terraform apply
```

Enabling the APIs takes a minute or two. Enabling Compute Engine also creates
a `default` network and a default service account in the project. Nothing uses
either.

### 6. Check

```
gcloud storage ls gs://prj-app-workboard-tfstate/workboard/
gcloud billing budgets list --billing-account=<ID>
terraform plan
```

The bucket holds `default.tfstate`, the budget is listed, and the last plan
reports no changes. The budget also appears in the console under Billing →
Budgets & alerts, where its alerts go to the billing account's
administrators.
