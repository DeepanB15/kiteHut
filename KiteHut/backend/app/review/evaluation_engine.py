"""
Phase 6 — Evaluation Metrics.
True positives, false positives, false negatives, precision, recall, F1.
"""
from dataclasses import dataclass
from typing import List

@dataclass
class EvaluationMetrics:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total > 0 else 0.0

    @property
    def recall(self) -> float:
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total > 0 else 0.0

    @property
    def f1(self) -> float:
        p = self.precision
        r = self.recall
        return (2 * p * r) / (p + r) if (p + r) > 0 else 0.0

class FindingEvaluator:
    def evaluate(self, actual_findings, expected_findings) -> EvaluationMetrics:
        # Simplified deterministic comparison by rule + file + line
        metrics = EvaluationMetrics()
        expected_keys = set()
        for f in expected_findings:
            key = (getattr(f, 'rule_id', ''), getattr(f, 'source_file', ''),
                   getattr(f, 'line_start', getattr(getattr(f, 'evidence', [None])[0], 'line_start', 0) if f.evidence else 0))
            expected_keys.add(key)

        actual_keys = set()
        for f in actual_findings:
            key = (getattr(f, 'rule_id', ''), getattr(f, 'source_file', ''),
                   getattr(f, 'evidence', [None])[0].line_start if f.evidence else 0)
            actual_keys.add(key)

        metrics.true_positives = len(actual_keys & expected_keys)
        metrics.false_positives = len(actual_keys - expected_keys)
        metrics.false_negatives = len(expected_keys - actual_keys)
        return metrics
