
"""Evaluation models for PHI extraction performance."""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class PHIMatch:
    """Represents a PHI entity for matching."""
    phi_type: str
    value: str
    start: int
    end: int

    def overlaps(self, other: "PHIMatch", tolerance: int = 5) -> bool:
        """Check if this entity overlaps with another (with position tolerance)."""
        return (
            self.phi_type == other.phi_type and
            abs(self.start - other.start) <= tolerance and
            abs(self.end - other.end) <= tolerance
        )

    def exact_match(self, other: "PHIMatch") -> bool:
        """Check for exact value and type match (position-independent)."""
        return self.phi_type == other.phi_type and self.value == other.value

    @classmethod
    def from_dict(cls, d: dict) -> "PHIMatch":
        return cls(
            phi_type=d["type"],
            value=d["value"],
            start=d.get("start", 0),
            end=d.get("end", 0)
        )


@dataclass
class EvaluationMetrics:
    """Metrics for a single note or aggregate evaluation."""
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        """Calculate precision: TP / (TP + FP)"""
        if self.true_positives + self.false_positives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_positives)

    @property
    def recall(self) -> float:
        """Calculate recall: TP / (TP + FN)"""
        if self.true_positives + self.false_negatives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_negatives)

    @property
    def f1_score(self) -> float:
        """Calculate F1 score: 2 * (P * R) / (P + R)"""
        p, r = self.precision, self.recall
        if p + r == 0:
            return 0.0
        return 2 * (p * r) / (p + r)

    def to_dict(self) -> dict:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4)
        }


@dataclass
class NoteEvaluation:
    """Evaluation results for a single note."""
    note_id: str
    overall_metrics: EvaluationMetrics = field(default_factory=EvaluationMetrics)
    metrics_by_type: Dict[str, EvaluationMetrics] = field(default_factory=dict)
    matched_entities: List[Tuple[PHIMatch, PHIMatch]] = field(default_factory=list)
    missed_entities: List[PHIMatch] = field(default_factory=list)  # False negatives
    extra_entities: List[PHIMatch] = field(default_factory=list)   # False positives

    def to_dict(self) -> dict:
        return {
            "note_id": self.note_id,
            "overall": self.overall_metrics.to_dict(),
            "by_type": {k: v.to_dict() for k, v in self.metrics_by_type.items()},
            "matched_count": len(self.matched_entities),
            "missed_count": len(self.missed_entities),
            "extra_count": len(self.extra_entities),
            "missed_entities": [{"type": e.phi_type, "value": e.value} for e in self.missed_entities],
            "extra_entities": [{"type": e.phi_type, "value": e.value} for e in self.extra_entities]
        }
