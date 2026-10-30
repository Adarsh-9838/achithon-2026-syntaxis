import pandas as pd


FEATURE_COLUMNS = ["signal_a", "signal_b", "region_mean_signal_a"]


def engineer_features(source: pd.DataFrame) -> pd.DataFrame:
    if source.empty:
        return pd.DataFrame(
            columns=["user_hash", "signal_a", "signal_b", "region_mean_signal_a"]
        )
    features = source[["user_hash", "region", "signal_a", "signal_b"]].copy()
    features["region_mean_signal_a"] = features.groupby("region")["signal_a"].transform(
        "mean"
    )
    return features[["user_hash", *FEATURE_COLUMNS]]
