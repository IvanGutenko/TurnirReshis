"""Прототип экспериментов для ноутбука (запуск: .venv/bin/python exp.py <config>)."""
import sys, time, warnings
warnings.filterwarnings("ignore")
import pandas as pd
from autogluon.timeseries import TimeSeriesDataFrame, TimeSeriesPredictor

DATA_DIR = "data/"
Q = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
train = pd.read_csv(DATA_DIR + "train.csv", parse_dates=["date"])


def add_features(df):
    df = df.copy()
    md = df["date"].dt.strftime("%m-%d")
    days_off = {"01-01", "01-02", "01-03", "01-04", "01-05", "01-06", "01-07", "01-08", "02-23", "03-08",
                "05-01", "05-02", "05-03", "05-09", "05-10", "06-12", "11-04", "12-29", "12-30", "12-31"}
    pre_holiday = {"12-29", "12-30", "12-31", "04-28", "04-29", "04-30", "05-01", "05-08", "05-09",
                   "06-10", "06-11", "11-02", "11-03", "02-22", "03-07", "01-08"}
    df["day_off"] = md.isin(days_off).astype(int)
    df["pre_holiday"] = md.isin(pre_holiday).astype(int)
    df["new_year_dip"] = md.isin({"01-01", "01-02"}).astype(int)
    df["back_to_work"] = md.isin({"01-09"}).astype(int)
    return df


def to_ts(df):
    return TimeSeriesDataFrame.from_data_frame(df.rename(columns={"route": "item_id", "date": "timestamp"}),
                                               id_column="item_id", timestamp_column="timestamp")


cfg = sys.argv[1]
feats = "_feat" in cfg
data = to_ts(add_features(train) if feats else train)
if "_static" in cfg:
    data.static_features = pd.DataFrame({"business": [int(i == "MOW-LED") for i in data.item_ids]}, index=data.item_ids)
kw = dict(prediction_length=31, target="demand", eval_metric="MAE", quantile_levels=Q,
          path=f"ag-exp-{cfg}", verbosity=1)
if feats:
    kw["known_covariates_names"] = ["day_off", "pre_holiday", "new_year_dip", "back_to_work"]
pred = TimeSeriesPredictor(**kw)
t = time.time()
base = cfg.replace("_feat", "").replace("_static", "")
if base in ("fast_training", "medium_quality", "high_quality"):
    pred.fit(data, presets=base, time_limit=900, num_val_windows=3)
elif base == "custom":
    pred.fit(data, num_val_windows=3, time_limit=1200, hyperparameters={
        "SeasonalNaive": {},
        "ETS": {},
        "Theta": {},
        "DirectTabular": {},
        "RecursiveTabular": {},
        "Chronos": [{"model_path": "bolt_small", "ag_args": {"name_suffix": "ZeroShot"}},
                    {"model_path": "bolt_small", "fine_tune": True, "ag_args": {"name_suffix": "FineTuned"}}],
    })
print(f"=== {cfg}: fit {time.time()-t:.0f}s")
print(pred.leaderboard()[["model", "score_val", "fit_time_marginal", "pred_time_val"]].to_string())
