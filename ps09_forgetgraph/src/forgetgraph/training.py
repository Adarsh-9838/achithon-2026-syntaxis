import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_COLUMNS


def fit_model(
    features: pd.DataFrame,
    targets: np.ndarray,
    alpha: float,
    random_seed: int,
) -> dict:
    matrix = features[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    estimator = Ridge(alpha=alpha, random_state=random_seed, solver="svd")
    estimator.fit(scaled, np.asarray(targets, dtype=np.float64))
    return {
        "feature_names": FEATURE_COLUMNS,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coefficients": estimator.coef_.tolist(),
        "intercept": float(estimator.intercept_),
        "alpha": float(alpha),
        "random_seed": int(random_seed),
    }


def predict(model: dict, features: pd.DataFrame) -> np.ndarray:
    matrix = features[model["feature_names"]].to_numpy(dtype=np.float64)
    scaled = (matrix - np.asarray(model["scaler_mean"])) / np.asarray(
        model["scaler_scale"]
    )
    return scaled @ np.asarray(model["coefficients"]) + model["intercept"]
