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

On a new project the plan only adds: nothing to change, nothing to destroy.
Then:

```
terraform apply
```

This takes 15 minutes or so, most of it the Cloud SQL instance. Enabling
Compute Engine also creates a `default` network and a default service account
in the project. Step 8 removes the network.

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

### 7. The application's secrets

Terraform writes `DATABASE_URL` itself, with a password nobody sees. The other
three come from you. Each value goes straight into Secret Manager, so it never
appears on screen or in shell history.

A fresh `SECRET_KEY`:

```
python3 -c 'import secrets, sys; sys.stdout.write(secrets.token_urlsafe(50))' \
  | gcloud secrets versions add SECRET_KEY --data-file=-
```

The sign-in client's ID and secret are the ones Render has, under the
service's Environment. Run this once for each. It waits for you to paste the
value and press Enter:

```
printf 'Value: '; read -rs VALUE; echo
printf '%s' "$VALUE" | gcloud secrets versions add GOOGLE_OAUTH_CLIENT_ID --data-file=-
unset VALUE
```

Then the same for `GOOGLE_OAUTH_CLIENT_SECRET`. To check, without printing any
value:

```
for s in DATABASE_URL SECRET_KEY GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET; do
  printf '%s: ' "$s"; gcloud secrets versions list "$s" --filter=state=enabled --format="value(name)" | wc -l
done
```

Each should have exactly 1.

### 8. Remove the default network

Google made it when Compute Engine was enabled. Nothing uses it, and its
firewall rules let SSH, RDP and ping in from anywhere. The rules go first,
since the network can't be deleted while they use it. Each command asks for
confirmation:

```
gcloud compute firewall-rules delete default-allow-icmp default-allow-internal \
  default-allow-rdp default-allow-ssh
gcloud compute networks delete default
gcloud compute networks list
```

Only `main` should be left.

## Releasing an image by hand

The pipeline does this on every push to `main`. By hand, it's for the first
image, or a release when the pipeline can't run. Commit first: the image is
tagged with the commit, so uncommitted changes would ship under a tag that
doesn't contain them.

Once per Mac, let Docker push to the registry:

```
gcloud auth configure-docker asia-southeast1-docker.pkg.dev
```

Then, from the repository root:

```
IMAGE=asia-southeast1-docker.pkg.dev/prj-app-workboard/workboard/workboard:$(git rev-parse HEAD)
docker buildx build --platform linux/amd64 --provenance=false -t "$IMAGE" --push .
gcloud run jobs update workboard-migrate --region=asia-southeast1 --image="$IMAGE"
gcloud run jobs execute workboard-migrate --region=asia-southeast1 --wait
gcloud run jobs update workboard-manage --region=asia-southeast1 --image="$IMAGE"
gcloud run services update workboard --region=asia-southeast1 --image="$IMAGE"
```

The order is the point. Migrations run to completion on the new image before
the service gets it, so new code never meets an old schema. A failed migration
stops there, with the old revision still serving. `--provenance=false` keeps
the build to a single image, so the registry's keep-5 rule counts releases
rather than build metadata.

`terraform plan` still reports no changes afterwards, because Terraform
ignores the image on the service and both jobs.

## Running a management command

`workboard-manage` runs any `manage.py` command against the production
database, with `--args` replacing the default `showmigrations`:

```
gcloud run jobs execute workboard-manage --region=asia-southeast1 --wait
gcloud run jobs execute workboard-manage --region=asia-southeast1 --wait \
  --args='^|^shell|-c|from accounts.models import User; print(User.objects.count())'
```

The `^|^` prefix makes `|` the separator, so the code can contain commas. To
read the output:

```
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="workboard-manage"' \
  --freshness=15m --order=asc --format="value(textPayload)"
```
