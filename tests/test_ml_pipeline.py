import pandas as pd
import pytest
from packages.ml.synthetic import make_synthetic
from packages.ml.data import load_vintages
from packages.ml.features import FEATURES,build_training_rows,features_asof
from packages.ml.publish_bundle import validate_bundle
from packages.ml.train import run_training
def test_synthetic_pipeline_and_bundle(tmp_path):
    csv=make_synthetic(tmp_path/"monthly.csv",months=60); raw=load_vintages(csv)
    rows=build_training_rows(raw,"demo_upi_count")
    assert len(rows)>20 and set(FEATURES).issubset(rows.columns)
    result=run_training(csv,tmp_path/"bundle","demo_upi_count")
    assert result["forecast"]["mode"]=="synthetic"
    assert result["forecast"]["lower"] is None
    assert validate_bundle(tmp_path/"bundle")["valid"]
def test_future_revision_does_not_change_old_origin_features(tmp_path):
    csv=make_synthetic(tmp_path/"monthly.csv",months=48); raw=load_vintages(csv)
    target=pd.Timestamp("2022-01-01",tz="UTC"); origin=pd.Timestamp("2021-12-20",tz="UTC")
    before=features_asof(raw,origin,target)[0]
    extra=pd.DataFrame([{"series_id":"demo_upi_count","period":pd.Timestamp("2021-10-01",tz="UTC"),
      "available_at":pd.Timestamp("2023-01-01",tz="UTC"),"revision":99,"volume_count":99999999}])
    after=features_asof(pd.concat([raw,extra],ignore_index=True),origin,target)[0]
    assert before==after
def test_bad_counts_rejected(tmp_path):
    csv=make_synthetic(tmp_path/"monthly.csv",months=24); df=pd.read_csv(csv)
    df.loc[0,"volume_count"]=-10; df.to_csv(csv,index=False)
    with pytest.raises(ValueError): load_vintages(csv)
