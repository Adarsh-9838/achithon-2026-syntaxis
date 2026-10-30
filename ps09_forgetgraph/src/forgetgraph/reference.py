import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_COLUMNS


def fit_independent_reference(
    feature_frame: pd.DataFrame,
    target_values: np.ndarray,
    alpha: float,
    random_seed: int,
) -> tuple[dict, np.ndarray]:
    raw_matrix = feature_frame.loc[:, FEATURE_COLUMNS].to_numpy(dtype=np.float64)
    target_array = np.asarray(target_values, dtype=np.float64)

    reference_scaler = StandardScaler(copy=True, with_mean=True, with_std=True)
    standardized_matrix = reference_scaler.fit_transform(raw_matrix)
    reference_estimator = Ridge(
        alpha=float(alpha),
        random_state=int(random_seed),
        solver="svd",
    )
    reference_estimator.fit(standardized_matrix, target_array)
    prediction_values = reference_estimator.predict(standardized_matrix)
    reference_model = {
        "feature_names": list(FEATURE_COLUMNS),
        "scaler_mean": reference_scaler.mean_.tolist(),
        "scaler_scale": reference_scaler.scale_.tolist(),
        "coefficients": reference_estimator.coef_.tolist(),
        "intercept": float(reference_estimator.intercept_),
        "alpha": float(alpha),
        "random_seed": int(random_seed),
    }
    return reference_model, prediction_values
