# Cloudflare deployment

## What runs on Cloudflare

The React/Vite dashboard is deployed to **Cloudflare Pages**. The current FastAPI + pandas + scikit-learn + XGBoost service remains a container workload (the repository's existing Render API service) and is called by the Pages frontend through `VITE_API_BASE_URL`.

This split is intentional: Cloudflare Python Workers support FastAPI, but the current training stack includes native/scientific dependencies and a batch-training workflow. Moving that workload into Workers without a tested compatible build would risk breaking the existing forecasting engine. Do not move XGBoost training into a Pages Function.

## One-time Cloudflare setup

1. Create a Cloudflare Pages project named `economic-pulse` and connect this GitHub repository, or let the workflow create the first deployment.
2. In GitHub repository Settings → Secrets and variables → Actions, add:
   - Secret `CLOUDFLARE_API_TOKEN` with Cloudflare Pages edit permissions.
   - Secret `CLOUDFLARE_ACCOUNT_ID`.
   - Optional secrets `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.
   - Optional variable `VITE_API_BASE_URL`; default is the existing API URL `https://economic-pulse-api.onrender.com`.
3. Ensure the API's CORS allowlist includes the final `*.pages.dev` domain and any custom domain.
4. Push to `main`. The Pages workflow builds `frontend/` and deploys `frontend/dist`.

## GitHub Actions workflow

The deploy workflow requires the two Cloudflare secrets. Pull requests run the build only; only pushes to `main` deploy. A missing Cloudflare credential fails the deployment job instead of silently claiming a deployment succeeded.

## Official RBI data source

The first official series is monthly UPI transaction volume from the RBI's *Entity-wise UPI/IMPS/NETC/NFS/AePS/CTS/BBPS Statistics* release page:

- RBI data releases catalogue: https://rbi.org.in/scripts/Statistics.aspx
- UPI/IMPS monthly release page: https://rbi.org.in/scripts/EntityWiseRetailStatistics.aspx
- RBI DBIE time-series portal: https://data.rbi.org.in/

The RBI page publishes workbook releases by month. Download the relevant RBI XLSX and use `packages/ml/ingest_rbi_xlsx.py` to convert a selected monthly aggregate into the vintage CSV format expected by the model. The adapter requires the exact RBI download URL, worksheet, period/value columns and actual release timestamp. It does not guess the aggregate row from bank/entity tables.

Example:

```bash
python -m packages.ml.ingest_rbi_xlsx \
  --input data/raw/rbi_upi.xlsx \
  --output data/processed/upi_monthly.csv \
  --source-url "https://rbidocs.rbi.org.in/..." \
  --sheet "UPI" \
  --period-column "Month" \
  --value-column "Volume" \
  --series-id upi_monthly \
  --available-at "2026-08-15T10:00:00+05:30"
```

The exact sheet and column names must be taken from the downloaded workbook. The adapter writes a SHA-256 provenance sidecar. Each workbook snapshot is revision 0; when RBI publishes a correction, ingest it as a later revision while preserving its actual availability timestamp. Do not invent release dates.

## Persistent Supabase training architecture

Apply migrations in this exact order in the Supabase SQL Editor or with the Supabase CLI:

1. `20261121000000_initial_user_data.sql`
2. `20261122000000_profiles_business_evidence_vault.sql`
3. `20261123000000_persistent_datasets_training_models.sql`

The third migration creates the `datasets`, `training_jobs`, `model_versions`, `model_evaluations` and `forecasts` tables; enables owner-scoped RLS; creates the private `economic-datasets` and `model-artifacts` buckets; and installs an atomic `SKIP LOCKED` queue-claim function. It does not replace the existing Evidence Vault.

### Runtime environment

Set these server-only environment variables on both the FastAPI API and the Render worker:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Never put the service-role key in Cloudflare Pages variables or any `VITE_*` variable. The frontend uses only `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.

The API verifies each caller's Supabase access token, checks dataset ownership and official-source URL provenance, then creates a PostgreSQL training job. The separate `economic-pulse-training-worker` claims queued jobs from Postgres, downloads the private CSV, trains and validates the model, uploads the bundle to `model-artifacts`, stores the evaluation and forecast rows, and publishes a version only after the evidence records are written.

### Worker deployment

The Render Blueprint adds a separate Python background worker. The worker currently uses the Render `starter` plan; confirm its price and availability in your Render account before provisioning. The existing API service remains separate. The dashboard remains on Cloudflare Pages.

### Official source allowlist

The training API currently accepts HTTPS source URLs under these official statistical domains: RBI, NPCI, MoSPI, data.gov.in, IMF, World Bank, OECD and FRED. The source URL is recorded in dataset metadata and model manifest. This validates the claimed source domain, not the byte-for-byte authenticity of a manually uploaded workbook. For RBI UPI, prefer the checked-in RBI XLSX adapter and preserve the actual release timestamp.

### Production verification still required

- Apply the three Supabase migrations to the intended project and verify both private buckets and RLS with two separate user accounts.
- Set the server-only Supabase environment variables on the API and worker.
- Provision and start the Render worker; verify it claims a queued job and recovers stale leases.
- Configure Cloudflare secrets and complete a main-branch Pages deployment.
- Run the first ingestion using the actual RBI workbook, then review chronological backtests and the reserved holdout before treating the forecast as decision-grade.
