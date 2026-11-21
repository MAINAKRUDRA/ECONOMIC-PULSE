# Economic Pulse forecasting engine

The first forecasting target is a **monthly UPI activity count**, not GDP. GDP/IIP forecasting is a separate future model with its own target definition, data vintages, baselines and out-of-time validation.

## Architecture

1. **Input:** CSV observation vintages with `series_id`, `period`, `available_at`, `revision`, and positive `volume_count`.
2. **As-of features:** only vintages available at a forecast origin are eligible. The model predicts `log(target_count / anchor_count)`.
3. **Baselines:** flat/last-known value, recent-trend extrapolation and an availability-checked seasonal-naive model.
4. **Challenger:** CPU XGBoost regression plus separate 10th, 50th and 90th quantile models.
5. **Evaluation:** expanding chronological origins with release-time eligibility. The latest 12 target months are reserved as a final holdout when history permits.
6. **Publication:** a validated bundle is atomically written to the API publication file. FastAPI serves the published bundle; normal read requests do not train models.

## Dataset format

The uploaded CSV must contain these columns:

| Column | Meaning |
|---|---|
| `series_id` | Stable identifier, e.g. `upi_monthly` |
| `period` | Reference month, ISO date on the first day, e.g. `2024-01-01` |
| `available_at` | Actual date/time this vintage became available |
| `revision` | Non-negative integer vintage number |
| `volume_count` | Positive numeric transaction count |

Use one series per training request. The current model is for monthly positive transaction counts. Values should be in a consistent unit across all periods. Do not fabricate publication dates or historical revisions. If you only have today's revised snapshot, use the actual capture date and understand that the data is not a full release-vintage archive.

## Backend training API

Configure these Render environment variables on the API service:

- `ECONOMIC_PULSE_ADMIN_TOKEN`: a long random secret; keep it private.
- `ECONOMIC_PULSE_ARTIFACT_DIR`: directory for uploaded CSVs, model artifacts and job files. Defaults to `/tmp/economic-pulse`.
- `ECONOMIC_PULSE_PUBLISHED_FILE`: optional full path to the published `current.json`. Defaults to `<ARTIFACT_DIR>/current.json`.

Upload a CSV (max 20 MB) with multipart form fields `series_id`, `source_name`, `rights_tag`, and the file field `file`:

```bash
curl -X POST "https://economic-pulse-api.onrender.com/v1/admin/train" \
  -H "Authorization: Bearer $ECONOMIC_PULSE_ADMIN_TOKEN" \
  -F "series_id=upi_monthly" \
  -F "source_name=RBI Payment System Indicators" \
  -F "rights_tag=reviewed-public-use" \
  -F "file=@monthly_upi_vintages.csv"
```

The response returns a `job_id`. Poll `GET /v1/admin/train/{job_id}` with the same Authorization header. A successful job validates and publishes a research bundle; the public `/v1/observations`, `/v1/forecasts`, `/v1/model-card` and `/v1/status` endpoints then read that batch.

**Storage warning:** Render's default filesystem is ephemeral. For durable production publication, mount a persistent disk and set `ECONOMIC_PULSE_ARTIFACT_DIR` and `ECONOMIC_PULSE_PUBLISHED_FILE` to paths on that disk, or move bundle storage to a durable object store before relying on it across deploys/restarts. The in-memory job-status registry is also instance-local.

## Local training

```bash
python -m pip install -r requirements-training.txt
python -m packages.ml.train --data /path/to/monthly_upi_vintages.csv --out artifacts/research-run --series-id upi_monthly --source-name "Approved source" --rights-tag "approved-public"
python -m packages.ml.publish_bundle artifacts/research-run --publish-to artifacts/published/current.json
```

## Evidence and interpretation

The bundle contains model artifacts (when XGBoost is available), feature schema, chronological baseline/challenger metrics, holdout diagnostics, forecast rows, observations, model card and a manifest with data/model hashes and training cutoff.

- XGBoost is promoted only when it beats the selected baseline on a sufficient common validation sample.
- Prediction bounds are withheld unless validation interval diagnostics meet minimum sample, coverage and crossing checks.
- Synthetic fixtures validate software plumbing only; they are not evidence of real forecast skill.
- UPI activity is not GDP. Do not describe these outputs as GDP forecasts.
