import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelConfig:
    alpha: float = 1.0
    random_seed: int = 42
    rtol: float = 1e-8
    atol: float = 1e-10


def load_config(path: Path | None) -> ModelConfig:
    if path is None:
        return ModelConfig()
    with path.open(encoding="utf-8") as file:
        values = json.load(file)
    config = ModelConfig(**values)
    if config.alpha <= 0 or config.rtol < 0 or config.atol < 0:
        raise ValueError("alpha must be positive and tolerances must be non-negative")
    return config
