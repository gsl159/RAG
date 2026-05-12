"""Nightly benchmark runner and regression detector.

Runs a curated test set against the current system configuration
and detects regressions from baseline.
"""

from __future__ import annotations

import asyncio
import json
import os
import time as _time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.shared.logging import logger


@dataclass
class BenchmarkCase:
    question: str
    expected_keywords: list[str]
    category: str = "general"
    min_confidence: float = 0.3


@dataclass
class BenchmarkResult:
    case: BenchmarkCase
    answer: str
    confidence: float
    keywords_matched: int
    total_keywords: int
    passed: bool
    latency_ms: int


class EvalRunner:
    """Runs benchmark evaluations and detects regressions."""

    DEFAULT_CASES = [
        BenchmarkCase("What is RAG?", ["retrieval", "augmented", "generation"], "definition"),
        BenchmarkCase("How does hybrid search work?", ["dense", "sparse", "BM25", "vector"], "technical"),
        BenchmarkCase("What are the benefits of semantic chunking?", ["chunk", "meaning", "context"], "technical"),
        BenchmarkCase("How to improve retrieval accuracy?", ["rerank", "embedding", "hybrid"], "how-to"),
        BenchmarkCase("Compare dense and sparse retrieval", ["dense", "sparse", "vector", "keyword"], "comparison"),
    ]

    def __init__(self, baseline_file: str = "eval_baseline.json"):
        self._lock = Lock()
        self._baseline_file = Path(baseline_file)
        self._baseline: dict[str, dict] = self._load_baseline()
        self._last_results: list[BenchmarkResult] = []

    def _load_baseline(self) -> dict:
        if self._baseline_file.exists():
            try:
                return json.loads(self._baseline_file.read_text())
            except Exception:
                pass
        return {}

    def _save_baseline(self) -> None:
        self._baseline_file.write_text(json.dumps(self._baseline, indent=2))

    async def run_benchmark(
        self, query_func, cases: list[BenchmarkCase] | None = None
    ) -> list[BenchmarkResult]:
        """Run benchmark cases and collect results."""
        cases = cases or self.DEFAULT_CASES
        results = []

        for case in cases:
            start = _time.monotonic()
            try:
                response = await query_func(case.question)
                answer = response.get("answer", "")
                confidence = response.get("confidence", 0.0)
            except Exception as e:
                logger.error("Benchmark case '{}' failed: {}", case.question, e)
                answer = ""
                confidence = 0.0

            elapsed_ms = int((_time.monotonic() - start) * 1000)

            # Check keyword matches
            answer_lower = answer.lower()
            matched = sum(1 for kw in case.expected_keywords if kw.lower() in answer_lower)
            passed = matched >= len(case.expected_keywords) * 0.5 and confidence >= case.min_confidence

            result = BenchmarkResult(
                case=case, answer=answer, confidence=confidence,
                keywords_matched=matched, total_keywords=len(case.expected_keywords),
                passed=passed, latency_ms=elapsed_ms,
            )
            results.append(result)

        with self._lock:
            self._last_results = results

        return results

    def get_summary(self) -> dict:
        """Return summary of last benchmark run."""
        with self._lock:
            if not self._last_results:
                return {"status": "no_results"}

            total = len(self._last_results)
            passed = sum(1 for r in self._last_results if r.passed)
            avg_latency = sum(r.latency_ms for r in self._last_results) / max(total, 1)
            avg_confidence = sum(r.confidence for r in self._last_results) / max(total, 1)

            by_category: dict[str, dict] = {}
            for r in self._last_results:
                cat = r.case.category
                if cat not in by_category:
                    by_category[cat] = {"total": 0, "passed": 0}
                by_category[cat]["total"] += 1
                if r.passed:
                    by_category[cat]["passed"] += 1

            return {
                "total_cases": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": passed / max(total, 1),
                "avg_latency_ms": round(avg_latency, 0),
                "avg_confidence": round(avg_confidence, 4),
                "by_category": by_category,
            }

    def detect_regression(self, threshold: float = 0.1) -> bool:
        """Check if current results show regression vs baseline."""
        summary = self.get_summary()
        baseline_rate = self._baseline.get("pass_rate", 1.0)
        current_rate = summary.get("pass_rate", 1.0)

        if baseline_rate - current_rate > threshold:
            logger.warning(
                "Regression detected: pass_rate dropped from {:.2%} to {:.2%}",
                baseline_rate, current_rate,
            )
            return True
        return False

    def update_baseline(self) -> None:
        """Set current results as the new baseline."""
        summary = self.get_summary()
        with self._lock:
            self._baseline = summary
            self._save_baseline()


_eval_runner = EvalRunner()

def get_eval_runner() -> EvalRunner:
    return _eval_runner
