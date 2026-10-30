import csv
import random
from pathlib import Path


SEED = 42
USER_COUNT = 700
REGIONS = ("North", "South", "East", "West")
OUTPUT = Path(__file__).parent / "data" / "synthetic_users.csv"


def generate_rows():
    rng = random.Random(SEED)
    for index in range(USER_COUNT):
        region_index = index % len(REGIONS)
        signal_a = rng.gauss(0.0, 1.0) + region_index * 0.2
        signal_b = rng.gauss(0.0, 1.0)
        target = (
            3.4 * signal_a
            - 2.1 * signal_b
            + 0.6 * region_index
            + rng.gauss(0.0, 0.35)
        )
        yield {
            "user_id": f"user-{index:04d}",
            "region": REGIONS[region_index],
            "signal_a": f"{signal_a:.10f}",
            "signal_b": f"{signal_b:.10f}",
            "target": f"{target:.10f}",
        }


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file, fieldnames=("user_id", "region", "signal_a", "signal_b", "target")
        )
        writer.writeheader()
        writer.writerows(generate_rows())
    print(f"Wrote {USER_COUNT} synthetic records to {OUTPUT}")
