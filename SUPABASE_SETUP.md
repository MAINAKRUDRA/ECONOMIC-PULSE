# Supabase setup — Economic Pulse

Supabase provides **user authentication and user-owned application data**. FastAPI remains the source for published observations, forecast batches, model cards and pulse calculations.

## 1. Apply the database migration

In the Supabase project dashboard:

1. Open **SQL Editor**.
2. Create a new query.
3. Run the migrations in timestamp order:
   - `20261121000000_initial_user_data.sql`
   - `20261122000000_profiles_business_evidence_vault.sql`
   - `20261123000000_persistent_datasets_training_models.sql`
4. Open **Table Editor** and confirm `profiles`, `saved_series`, `datasets`, `training_jobs`, `model_versions`, `model_evaluations` and `forecasts` exist.
5. Open **Storage** and confirm `evidence-vault`, `economic-datasets` and `model-artifacts` are private buckets.
6. In **Authentication → Providers**, enable Email. Decide whether email confirmation should be required before launch.

The migration enables RLS on both tables. Each signed-in user can only read or modify rows where their user ID matches `auth.uid()`. Never disable RLS to make the frontend work.

## 2. Configure the frontend

For the repository's GitHub Actions deployment workflow, add these as GitHub Actions secrets (`Settings → Secrets and variables → Actions`):

- `VITE_SUPABASE_URL` — Supabase project URL.
- `VITE_SUPABASE_PUBLISHABLE_KEY` — Supabase publishable key.

If you instead connect Cloudflare Pages directly to GitHub and build there, set the same two values in Cloudflare Pages → Settings → Environment variables. The current workflow reads them from GitHub Actions secrets at build time.

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

## 7. Persistent dataset and model pipeline

The third migration creates the private `economic-datasets` and `model-artifacts` buckets, dataset metadata, durable training jobs, model versions, evaluation reports and forecast records. RLS restricts dataset, job, model, evaluation and forecast reads to the owning account. Dataset Storage paths must begin with the user's UUID. Only the verified API service role can enqueue a training job; browser clients cannot insert arbitrary queue jobs.

The Model Training panel uploads CSV files directly to `economic-datasets`, registers metadata in `datasets`, then calls the FastAPI queue endpoint with the current Supabase access token. The API verifies the token, confirms ownership and checks the official source URL allowlist before it inserts a job.

## 8. Server-only secrets and worker

Set the following environment variables on **both** the FastAPI API service and the separate Render background worker:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

The service-role key bypasses RLS and must remain server-only. Never add it to Cloudflare Pages, GitHub frontend variables, `VITE_*` variables, or source control. The browser uses only the publishable key.

The worker claims jobs from PostgreSQL using the migration's atomic `claim_economic_pulse_training_job()` function, downloads the private dataset, runs the existing training/backtest pipeline, uploads the complete bundle to `model-artifacts`, saves an evaluation report and forecast rows, and marks the model version published only after those records are stored.

## 9. Two-user permission test

Use two separate test accounts:

1. Upload a CSV and start training as account A.
2. Confirm account A can see its dataset, job and model history.
3. Sign in as account B and confirm it cannot list account A's dataset, job, model version, evaluation or forecast.
4. Attempt to access an account A Storage object using account B's session; it must be denied.
5. Confirm the API rejects account B's attempt to queue account A's dataset.

The automated suite mocks Supabase network calls; this two-account test must still be completed against the live project after applying the migrations.
