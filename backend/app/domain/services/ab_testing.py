"""A/B testing framework for comparing retrieval and generation strategies.

Supports traffic splitting, statistical significance testing,
and automatic promotion of winning strategies.
"""

from __future__ import annotations

import random
import time as _time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Awaitable


@dataclass
class Experiment:
    """An A/B test experiment comparing two strategies."""
    name: str
    strategy_a: str  # control
    strategy_b: str  # treatment
    traffic_split: float = 0.5  # fraction going to B
    min_samples: int = 100
    confidence_threshold: float = 0.95
    created_at: float = field(default_factory=_time.monotonic)

    # Results
    a_scores: list[float] = field(default_factory=list)
    b_scores: list[float] = field(default_factory=list)
    concluded: bool = False
    winner: str = ""


class ABTestingFramework:
    """Manages A/B test experiments for continuous optimization."""

    def __init__(self):
        self._lock = Lock()
        self._experiments: dict[str, Experiment] = {}

    def create_experiment(
        self, name: str, strategy_a: str, strategy_b: str,
        traffic_split: float = 0.5, min_samples: int = 100
    ) -> Experiment:
        with self._lock:
            exp = Experiment(
                name=name, strategy_a=strategy_a, strategy_b=strategy_b,
                traffic_split=traffic_split, min_samples=min_samples,
            )
            self._experiments[name] = exp
            return exp

    def should_use_b(self, experiment_name: str) -> bool:
        """Determine which strategy to use for this request."""
        with self._lock:
            exp = self._experiments.get(experiment_name)
            if exp is None or exp.concluded:
                return False
            return random.random() < exp.traffic_split

    def record_result(self, experiment_name: str, used_b: bool, score: float) -> None:
        """Record a quality score from a completed request."""
        with self._lock:
            exp = self._experiments.get(experiment_name)
            if exp is None or exp.concluded:
                return

            if used_b:
                exp.b_scores.append(score)
            else:
                exp.a_scores.append(score)

            # Check if we have enough data to conclude
            if len(exp.a_scores) >= exp.min_samples and len(exp.b_scores) >= exp.min_samples:
                self._check_conclusion(exp)

    def _check_conclusion(self, exp: Experiment) -> None:
        """Check if B is statistically significantly better than A."""
        import statistics

        mean_a = statistics.mean(exp.a_scores) if exp.a_scores else 0
        mean_b = statistics.mean(exp.b_scores) if exp.b_scores else 0

        # Simple Z-test approximation
        std_a = statistics.stdev(exp.a_scores) if len(exp.a_scores) > 1 else 0.1
        std_b = statistics.stdev(exp.b_scores) if len(exp.b_scores) > 1 else 0.1
        n_a, n_b = len(exp.a_scores), len(exp.b_scores)

        se = ((std_a ** 2 / n_a) + (std_b ** 2 / n_b)) ** 0.5
        if se == 0:
            return

        z_score = abs(mean_b - mean_a) / se

        if z_score >= 1.96:  # 95% confidence
            exp.concluded = True
            exp.winner = "B" if mean_b > mean_a else "A"

    def get_active_experiments(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "name": e.name,
                    "a": e.strategy_a, "b": e.strategy_b,
                    "a_samples": len(e.a_scores), "b_samples": len(e.b_scores),
                    "a_mean": sum(e.a_scores) / max(len(e.a_scores), 1),
                    "b_mean": sum(e.b_scores) / max(len(e.b_scores), 1),
                    "concluded": e.concluded,
                    "winner": e.winner,
                }
                for e in self._experiments.values()
            ]


_ab_framework = ABTestingFramework()

def get_ab_framework() -> ABTestingFramework:
    return _ab_framework
