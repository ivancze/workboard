# Copying the data from Neon to Cloud SQL

> **A record, not a procedure to follow.** The move was done on 2026-10-14,
> and Render and Neon have since been deleted. It's kept for how the copy and
> the cutover went.

Used once for the trial run and once at switch-over. Everything runs from the
repository root on the operator's Mac, with Compose up. The Mac has no Postgres
client of its own, so `pg_dump` runs in the `db` container, which is the same
version as Neon, 17.11.

The dump holds Members' email addresses. It never goes into the repository,
and both copies of it are deleted at the end.

## 1. Neon's address

Copy `DATABASE_URL` from the Render service's Environment, and paste it at the
prompt. It's the direct endpoint, not `-pooler`; see
[deployment.md](deployment.md). It stays out of shell history and off the
screen:

```
printf 'Neon URL: '; read -rs NEON_URL; echo
DUMP="$TMPDIR/workboard.sql"
```

## 2. Dump

```
time (printf '%s\n' "$NEON_URL" | docker compose exec -T db sh -c \
  'read -r URL; pg_dump "$URL" --format=plain --no-owner --no-privileges --clean --if-exists' > "$DUMP")
ls -lh "$DUMP"
```

- **Plain SQL** is what Cloud SQL imports.
- **`--no-owner --no-privileges`:** Neon's roles don't exist in Cloud SQL, so
  everything ends up owned by the user running the import.
- **`--clean --if-exists`** drops each table before recreating it. Cloud SQL
  already holds the schema from the migration job, and anything written there
  since.

## 3. Count Neon's rows

Right after the dump. During the trial run Render is still serving, so Neon can
move on, and a session or two may be added between the dump and the count.

```
printf '%s\n' "$NEON_URL" | docker compose run --rm --no-deps -T web sh -c \
  'read -r DATABASE_URL; export DATABASE_URL; python manage.py table_counts' | LC_ALL=C sort > "$TMPDIR/neon-counts.txt"
```

## 4. Upload and import

The import runs on Google's side as the instance's service account, which may
read the dumps bucket.

```
gcloud storage cp "$DUMP" gs://prj-app-workboard-dumps/workboard.sql
time gcloud sql import sql workboard gs://prj-app-workboard-dumps/workboard.sql \
  --database=workboard --user=workboard --quiet
```

`pg_dump` 17.6 and later wrap the dump in `\restrict` and `\unrestrict`, which
older `psql` versions don't know. If the import fails with "invalid command
\restrict", remove those two lines, upload again and repeat the import:

```
sed -i '' -e '/^\\restrict /d' -e '/^\\unrestrict /d' "$DUMP"
gcloud storage cp "$DUMP" gs://prj-app-workboard-dumps/workboard.sql
```

## 5. Count Cloud SQL's rows and compare

```
EXECUTION=$(gcloud run jobs execute workboard-manage --region=asia-southeast1 --wait \
  --args=table_counts --format='value(metadata.name)')
gcloud logging read "resource.type=\"cloud_run_job\" AND labels.\"run.googleapis.com/execution_name\"=\"$EXECUTION\"" \
  --freshness=1h --format='value(textPayload)' | grep -E '^[a-z_]+ [0-9]+$' | LC_ALL=C sort > "$TMPDIR/cloudsql-counts.txt"
diff "$TMPDIR/neon-counts.txt" "$TMPDIR/cloudsql-counts.txt" && echo "Counts match."
```

Any difference in a table other than `django_session` is a problem to raise,
not to fix by hand.

## 6. Delete every copy

```
gcloud storage rm gs://prj-app-workboard-dumps/workboard.sql
rm "$DUMP" "$TMPDIR/neon-counts.txt" "$TMPDIR/cloudsql-counts.txt"
unset NEON_URL DUMP EXECUTION
```

The bucket also deletes anything older than a day, in case this step is
forgotten.
