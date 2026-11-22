# Supabase setup — Economic Pulse

Supabase provides **user authentication and user-owned application data**. FastAPI remains the source for published observations, forecast batches, model cards and pulse calculations.

## 1. Apply the database migration

In the Supabase project dashboard:

1. Open **SQL Editor**.
2. Create a new query.
3. Paste and run `supabase/migrations/20261121000000_initial_user_data.sql`.
4. Open **Table Editor** and confirm `profiles` and `saved_series` exist.
5. In **Authentication → Providers**, enable Email. Decide whether email confirmation should be required before launch.

The migration enables RLS on both tables. Each signed-in user can only read or modify rows where their user ID matches `auth.uid()`. Never disable RLS to make the frontend work.

## 2. Configure the frontend

Set these variables in the frontend hosting service (Render Static Site → Environment):

- `VITE_SUPABASE_URL` — Supabase project URL.
- `VITE_SUPABASE_PUBLISHABLE_KEY` — Supabase publishable key.

The publishable key is designed for browser use; RLS is the security boundary. **Never put a Supabase secret or service-role key in a `VITE_*` variable or frontend code.**

For local development, copy `frontend/.env.example` to `frontend/.env.local` and fill in the same two values. Restart Vite after changing environment variables.

## 3. Configure authentication URLs

In Supabase **Authentication → URL Configuration**:

- Set the Site URL to the deployed frontend URL.
- Add the deployed frontend URL and local development URL (for example `http://localhost:5173`) to the Redirect URLs allow-list.

The current MVP uses email/password sign-up and sign-in; it does not implement OAuth or password-reset UI.

## 4. Verify the integration

1. Open the frontend and select **Sign in / Create account**.
2. Create a test account using an email address you control.
3. Confirm the email if confirmation is enabled.
4. Sign in and select **Save demo series**.
5. Confirm the row appears under `saved_series` in Table Editor.
6. Sign out and sign in again; the saved series should remain.
7. In Table Editor, verify another user cannot read the first user's row (RLS is enforced on API requests).

## Data boundaries

- Supabase: identities, profiles and per-user saved-series/watchlist records.
- FastAPI: read-only economic observations, forecasts, model cards and pulse endpoints.
- ML workflow: offline training, backtesting and validated publication bundles.

The current saved-series button saves the existing illustrative `demo_upi` series. It does not convert synthetic demo observations into official economic data.


## 5. Apply the profile and Evidence Vault migration

After the initial user-data migration has been applied, run the second migration:

`supabase/migrations/20261122000000_profiles_business_evidence_vault.sql`

This adds personal profile fields (full name, phone, account type and role), optional business fields, an `evidence_files` metadata table, and a **private** Storage bucket named `evidence-vault`.

The frontend supports personal and business accounts. Business fields are optional unless the user selects Business. The vault accepts PDF, DOC/DOCX, XLS/XLSX, CSV, TXT, JPG, PNG and WEBP files up to 20 MB each. Files are uploaded into a folder named with the authenticated user's UUID. Storage policies enforce that folder ownership; metadata rows also have RLS.

Downloads use short-lived signed URLs (60 seconds). The bucket must remain private. Do not make it public or remove the Storage RLS policies.

## 6. Profile and evidence verification

1. Sign in with a test account and complete the personal profile.
2. Switch Account type to Business, fill in the optional business fields, and save.
3. Upload one test PDF in the Evidence Vault.
4. Confirm the file appears in the private `evidence-vault` bucket and its metadata appears in `evidence_files`.
5. Download it from the UI; the download uses a temporary signed URL.
6. Sign in as a different test user and confirm the first user's metadata and file cannot be listed or downloaded.
7. Delete the test file and confirm both the Storage object and metadata row are removed.

Collect only business registration information that is actually needed. Do not upload passwords, API keys, payment-card data, or unnecessary identity documents.


## 7. Production ML persistence (third migration)

Run the complete SQL contents of
`supabase/migrations/20261122150000_production_ml_persistence.sql`
in the Supabase SQL Editor, after the two migrations above. Do not paste the filename itself.

This migration creates owner-scoped `datasets`, `training_jobs` and
`model_artifacts` tables, a published-bundle registry, and private
`economic-datasets` and `model-artifacts` Storage buckets. RLS protects
user-visible records and Storage paths. The API uses a server-only service
role key and verifies each user's Supabase access token before accepting
training requests or returning a job.

### Render API environment

Set these variables on the Render `economic-pulse-api` service:

- `SUPABASE_URL` — the Supabase project URL.
- `SUPABASE_SERVICE_ROLE_KEY` — the server-side service-role key from the
  Supabase project API settings. Keep this secret; never add it to the
  frontend, a `VITE_*` variable, source control, or client logs.

Keep `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` on the frontend
service only. After changing the API environment, allow Render to restart.

### Production verification

1. Sign in to Economic Pulse.
2. Open Model training and upload a permitted CSV.
3. Confirm a row appears in `datasets` and `training_jobs`.
4. Confirm the CSV object appears in the private `economic-datasets` bucket.
5. Poll the job and verify its status is persisted after refreshing the page.
6. After a successful run, confirm a `model_artifacts` row, an object in
   `model-artifacts`, and a row in `published_bundles`.
7. Sign in as a second user and verify the first user's datasets and jobs
   are not returned.

The API currently executes training as a FastAPI background task. Job state,
input datasets, artifacts and publication bundles are stored in Supabase;
a separate durable worker/queue is still recommended before high-volume use.
