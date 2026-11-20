# Economic Pulse forecasting engine

The first forecasting target is a **monthly UPI activity count**, not GDP. GDP/IIP forecasting is a separate future model with its own target definition, data vintages, baselines and out-of-time validation.

## Architecture

1. **Input:** a CSV of immutable observation vintages with `series_id`, `period`, `available_at`, `revision`, and positive `volume_count`.
2. **As-of features:** only vintages available at the forecast origin are eligible. The model predicts `log(target_count / anchor_count)`; predictions are converted back with `anchor_count * exp(log_change)`.
3. **Baselines:** flat/last-known value, recent-trend extrapolation and an availability-checked seasonal-naive model.
4. **Challenger:** CPU XGBoost regression plus separate 10th, 50th and 90th quantile models.
5. **Evaluation:** expanding chronological origins with release-time eligibility. The latest 12 target months are reserved as a final holdout when history permits. Model selection never uses that holdout.
6. **Publication:** a validated, hashed bundle is produced offline. FastAPI reads the approved bundle; HTTP requests do not start training.

## Run locally or in Colab

From the repository root:

```bash
python -m pip install -r requirements-training.txt
python -m packages.ml.synthetic --out data/synthetic/monthly_upi_demo.csv --months 60
python -m packages.ml.train --data data/synthetic/monthly_upi_demo.csv --out artifacts/synthetic-demo --series-id demo_upi_count
python -m packages.ml.publish_bundle artifacts/synthetic-demo
```

To atomically create a local API publication file after validation:

```bash
python -m packages.ml.publish_bundle artifacts/synthetic-demo --publish-to artifacts/published/current.json
```

Set `ECONOMIC_PULSE_PUBLISHED_FILE` on the API process only when the bundle has been reviewed and copied to durable storage. Do not assume Render's ephemeral filesystem is durable.

## Real-data run

Use only data with documented source rights and release timestamps. Keep the original CSV outside public source control. Supply provenance explicitly:

```bash
python -m packages.ml.train \
  --data /path/to/approved/monthly_upi_vintages.csv \
  --out artifacts/research-run \
  --series-id upi_monthly \
  --source-name "Approved source name" \
  --rights-tag "approved-public"
```

A research run is rejected if source name or rights tag is absent. Never replace historical first-release vintages with today's revised values.

## Evidence and interpretation

The bundle contains the model artifacts (when XGBoost is available), feature schema, chronological baseline/challenger metrics, holdout diagnostics, forecast rows, observations, model card and a manifest with data/model hashes and training cutoff.

- XGBoost is promoted only when it beats the selected baseline on a sufficient common validation sample.
- Prediction bounds are withheld unless the validation interval diagnostics meet the minimum sample, coverage and crossing checks.
- Quantile crossing is measured and reported; sorting crossed bounds is not treated as calibration.
- Synthetic training verifies software plumbing only. It is not evidence of real UPI forecast skill.
- UPI activity is not GDP. Do not describe these outputs as GDP forecasts or macroeconomic growth estimates.

GitHub Actions runs the unit tests and a bounded synthetic training/publication check on ML-related changes. The generated evidence is retained as a short-lived CI artifact, not automatically published to the production API.
