# Economic Pulse

**Cosmo Advisory Co — experimental monthly UPI activity forecasting research**

React + FastAPI application with a separate, offline Python ML workflow. The model workflow follows the Economic Pulse specification: vintage-aware monthly observations, as-of features, expanding chronological validation, naive baselines, a conservative XGBoost challenger, quantile diagnostics and a locally validated forecast bundle.

## Important data and claims boundary

The included generator creates **synthetic data only**. It tests code paths; it is not NPCI data, a UPI estimate, evidence of economic forecasting performance, or a GDP forecast. Replace it only with an approved, rights-cleared source archive containing real release timestamps and revisions. Forecasting UPI activity does not validate GDP/IIP forecasting.

## ML engine layout

- `packages/ml/data.py`: strict input validation and SHA-256 source snapshot hash.
- `features.py`: release-time/as-of feature builder; refuses missing or non-consecutive trailing history.
- `baselines.py`: flat, trend and availability-eligible seasonal-naive baselines.
- `backtest.py`: expanding chronological folds and reserved latest 12 target months where history allows.
- `challenger.py`: XGBoost point/quantile challenger, common-fold comparison, pinball loss, interval coverage/width and quantile crossing checks.
- `train.py`: trains offline, selects a champion only when it beats the strongest baseline on common validation rows, exports forecasts/evidence/model card.
- `publish_bundle.py`: validates a local export before a separate publication process.

Training and XGBoost are intentionally **not** dependencies of the FastAPI serving process. API requests never start training.

## Run the ML pipeline (Python 3.11 recommended)

From the repository root:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-training.txt

# Generate a synthetic pipeline fixture (not real economic data)
python -m packages.ml.synthetic --months 60

# Train, backtest and export a local research bundle
python -m packages.ml.train --data data/synthetic/monthly_upi_demo.csv --out artifacts/research --series-id demo_upi_count

# Validate the export contract
python -m packages.ml.publish_bundle artifacts/research --publish-to artifacts/published/current.json
# Point the read-only API at that atomically switched local publication file:
# ECONOMIC_PULSE_PUBLISHED_FILE=../artifacts/published/current.json uvicorn app.main:app --reload

# Run automated tests
python -m pytest -q
```

The local export contains `forecast_rows.json`, `features.json`, `manifest.json`, `backtest.json`, `challenger_validation.json`, `model_card.md` and model files when XGBoost is available. Keep research bundles and model artifacts outside public source control.

## Input CSV contract

Required columns: `series_id,period,available_at,revision,volume_count`.

- `period`: first day of a completed reference month.
- `available_at`: UTC time when that particular vintage was actually available.
- `revision`: source revision number; preserve revisions.
- `volume_count`: positive finite transaction count.

The worked origin policy builds each historical forecast at 00:00 UTC on the 20th of the month before the target month. The target is log(target-month count / latest count known at origin); conversion back uses the same known anchor. This is anchor-to-target growth, not automatically month-on-month growth.

## Model governance

- Features use only vintages available at the forecast origin; target labels use their first released vintage.
- Training eligibility requires both an earlier forecast origin and labels available by that origin.
- Final latest-12-month holdout is reserved when history is sufficient and is not used for selection.
- XGBoost is a challenger, not the default champion. A baseline remains selected if it performs better.
- 10th/50th/90th quantile models are checked for pinball loss, empirical 80% interval coverage, width and crossing. Bounds are withheld unless minimum validation sample and coverage checks pass.
- Synthetic mode is explicit in exported artifacts. Do not market synthetic metrics or outputs as economic evidence.
- Source rights, data vintages, coverage changes and review approval are required before real-data publication.

## Frontend and API

Frontend: React + TypeScript + Vite on Cloudflare Pages. API: FastAPI on Render. Supabase provides email/password authentication, owner-scoped datasets, a PostgreSQL training queue, model-version history, evaluations and forecasts. The separate Render worker performs offline training. See [SUPABASE_SETUP.md](SUPABASE_SETUP.md) and [CLOUDFLARE_DEPLOYMENT.md](CLOUDFLARE_DEPLOYMENT.md) for configuration.

```bash
cd backend
python -m venv .venv
# activate the environment
pip install -r requirements.txt
uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

API docs: http://127.0.0.1:8000/docs · Frontend: http://localhost:5173

The read-only API can serve the validated local publication file through ECONOMIC_PULSE_PUBLISHED_FILE. This local file switch is for the MVP only; hosted multi-user publication should use the specification’s database-backed staged batch and atomic publication-head transaction. Do not copy model artifacts into the serving container.

## Official RBI data ingestion

The initial official-data adapter is `packages/ml/ingest_rbi_xlsx.py`. It converts an operator-selected RBI monthly XLSX aggregate into the model's vintage CSV contract and writes a SHA-256 provenance sidecar. It requires the exact worksheet, columns, official RBI download URL and actual release timestamp; it does not infer totals from entity-level rows. See [CLOUDFLARE_DEPLOYMENT.md](CLOUDFLARE_DEPLOYMENT.md) for the source catalogue and deployment setup.

## Cloudflare Pages

The dashboard's Cloudflare Pages build/deploy workflow is [cloudflare-pages.yml](.github/workflows/cloudflare-pages.yml). Configure `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` GitHub Actions secrets before deploying. The FastAPI/ML API remains a separate Python container service; see [CLOUDFLARE_DEPLOYMENT.md](CLOUDFLARE_DEPLOYMENT.md).

## Persistent training pipeline

The signed-in Model Training panel uploads CSV files directly to the private Supabase Storage bucket `economic-datasets`, then registers dataset metadata under the authenticated user's PostgreSQL identity. The API verifies the Supabase access token and dataset ownership before creating a durable `training_jobs` row. A separate Render background worker claims jobs through a Postgres `SKIP LOCKED` function; training no longer runs in FastAPI background tasks or an in-memory dictionary.

Validated bundles are written to the private `model-artifacts` bucket. The model registry stores version history, source provenance, metrics, forecast payloads and evaluation reports. Forecast endpoints return the latest published model for the signed-in user, and the dashboard refreshes when the session changes.

Apply migrations in timestamp order, including `20261123000000_persistent_datasets_training_models.sql`, after the existing profile and Evidence Vault migrations. Configure `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` on the API and worker only. Never expose the service-role key to the browser. The full deployment and verification checklist is in [CLOUDFLARE_DEPLOYMENT.md](CLOUDFLARE_DEPLOYMENT.md).
