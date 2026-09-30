from collections import defaultdict
from pathlib import Path
import json
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from .real_models import RealPlayerGameStat

NFL_METRICS = ("passing_yards", "rushing_yards", "receiving_yards", "receptions")


def evaluate_nfl_baseline(session: Session, output_path: str = "data/reports/nfl_baseline_evaluation.json") -> dict:
    rows = list(session.scalars(select(RealPlayerGameStat).where(RealPlayerGameStat.sport == "NFL").order_by(RealPlayerGameStat.game_date)))
    grouped: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    for row in rows:
        for metric in NFL_METRICS:
            value = row.values.get(metric)
            if isinstance(value, (int, float)):
                grouped[(row.player_id, metric)].append((row.game_date, float(value)))
    report = {"model_version": "nflverse-recency-baseline-v1", "data_mode": "historical", "metrics": {}}
    for metric in NFL_METRICS:
        errors: list[float] = []
        for (player_id, current_metric), observations in grouped.items():
            if current_metric != metric:
                continue
            for index in range(3, len(observations)):
                prior = [value for _, value in observations[max(0, index - 5):index]]
                prediction = sum(prior) / len(prior)
                errors.append(observations[index][1] - prediction)
        if errors:
            report["metrics"][metric] = {
                "sample_size": len(errors),
                "mae": sum(abs(error) for error in errors) / len(errors),
                "rmse": math.sqrt(sum(error * error for error in errors) / len(errors)),
                "evaluation": "chronological rolling prior-5 mean",
            }
        else:
            report["metrics"][metric] = {"sample_size": 0, "status": "insufficient_data"}
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
