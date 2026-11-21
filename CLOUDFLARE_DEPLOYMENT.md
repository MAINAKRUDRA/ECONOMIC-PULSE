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

## Production blockers that remain

- Configure Cloudflare account secrets and verify the first Pages deployment.
- Confirm the actual RBI workbook's sheet/column mapping and run the adapter against the official workbook.
- Add a durable database/object-store publication registry and persistent training queue. The current API training route uses process memory and a local filesystem path and is not restart-safe.
- Verify Supabase migrations, auth and RLS against the live project.
- Run real-data expanding-window backtests and reserved holdout evaluation before publishing an official-data forecast.
