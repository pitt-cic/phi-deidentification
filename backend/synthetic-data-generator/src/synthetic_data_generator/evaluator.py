"""Evaluation module for comparing de-identification results against ground truth."""

import json
from pathlib import Path
from typing import List, Optional, Tuple

from .models.eval_models import EvaluationMetrics, NoteEvaluation, PHIMatch


class Evaluator:
    """Evaluate de-identification solution output against ground truth."""

    def __init__(self, match_mode: str = "value"):
        """
        Initialize evaluator.

        Args:
            match_mode: How to match entities
                - "value": Match by type and value (position-independent)
                - "position": Match by type and position overlap
                - "strict": Match by type, value, AND position
        """
        self.match_mode = match_mode

    def load_ground_truth(self, manifest_path: Path) -> List[PHIMatch]:
        """Load ground truth entities from manifest file."""
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

        return [PHIMatch.from_dict(e) for e in manifest.get("phi_entities", [])]

    def load_solution_output(self, output_path: Path) -> List[PHIMatch]:
        """
        Load solution output entities.

        Expected format:
        {
            "phi_entities": [
                {"type": "NAME", "value": "John Doe"},
                {"type": "SSN", "value": "123-45-6789"}
            ]
        }
        """
        with open(output_path, 'r') as f:
            output = json.load(f)

        return [PHIMatch.from_dict(e) for e in output.get("phi_entities", [])]

    def _match_entities(
        self,
        ground_truth: List[PHIMatch],
        predictions: List[PHIMatch]
    ) -> Tuple[List[Tuple[PHIMatch, PHIMatch]], List[PHIMatch], List[PHIMatch]]:
        """
        Match predicted entities to ground truth.

        Returns:
            - matched: List of (ground_truth, prediction) tuples
            - missed: Ground truth entities not found (false negatives)
            - extra: Predicted entities not in ground truth (false positives)
        """
        matched = []
        gt_matched = set()
        pred_matched = set()

        # Match based on mode
        for i, gt in enumerate(ground_truth):
            for j, pred in enumerate(predictions):
                if j in pred_matched:
                    continue

                is_match = False
                if self.match_mode == "value":
                    is_match = gt.exact_match(pred)
                elif self.match_mode == "position":
                    is_match = gt.overlaps(pred)
                elif self.match_mode == "strict":
                    is_match = gt.exact_match(pred) and gt.overlaps(pred, tolerance=0)

                if is_match:
                    matched.append((gt, pred))
                    gt_matched.add(i)
                    pred_matched.add(j)
                    break

        # Find unmatched
        missed = [gt for i, gt in enumerate(ground_truth) if i not in gt_matched]
        extra = [pred for j, pred in enumerate(predictions) if j not in pred_matched]

        return matched, missed, extra

    def evaluate_note(
        self,
        ground_truth: List[PHIMatch],
        predictions: List[PHIMatch]
    ) -> NoteEvaluation:
        """
        Evaluate predictions against ground truth for a single note.

        Args:
            ground_truth: List of ground truth PHI entities
            predictions: List of predicted PHI entities

        Returns:
            NoteEvaluation with metrics
        """
        matched, missed, extra = self._match_entities(ground_truth, predictions)

        # Calculate overall metrics
        overall = EvaluationMetrics(
            true_positives=len(matched),
            false_positives=len(extra),
            false_negatives=len(missed)
        )

        # Calculate metrics by PHI type
        metrics_by_type = {}
        all_types = set(e.phi_type for e in ground_truth + predictions)

        for phi_type in all_types:
            type_gt = [e for e in ground_truth if e.phi_type == phi_type]
            type_pred = [e for e in predictions if e.phi_type == phi_type]
            type_matched, type_missed, type_extra = self._match_entities(type_gt, type_pred)

            metrics_by_type[phi_type] = EvaluationMetrics(
                true_positives=len(type_matched),
                false_positives=len(type_extra),
                false_negatives=len(type_missed)
            )

        return NoteEvaluation(
            note_id="",
            overall_metrics=overall,
            metrics_by_type=metrics_by_type,
            matched_entities=matched,
            missed_entities=missed,
            extra_entities=extra
        )

    def evaluate_from_files(
        self,
        ground_truth_path: Path,
        solution_output_path: Path,
        note_id: Optional[str] = None
    ) -> NoteEvaluation:
        """
        Evaluate from file paths.

        Args:
            ground_truth_path: Path to ground truth manifest JSON
            solution_output_path: Path to solution output JSON
            note_id: Optional note ID (extracted from filename if not provided)

        Returns:
            NoteEvaluation with metrics
        """
        if note_id is None:
            note_id = ground_truth_path.stem

        ground_truth = self.load_ground_truth(ground_truth_path)
        predictions = self.load_solution_output(solution_output_path)

        evaluation = self.evaluate_note(ground_truth, predictions)
        evaluation.note_id = note_id

        return evaluation

    def evaluate_batch(
        self,
        ground_truth_dir: Path,
        solution_output_dir: Path
    ) -> Tuple[List[NoteEvaluation], EvaluationMetrics]:
        """
        Evaluate all notes in directories.

        Args:
            ground_truth_dir: Directory containing ground truth manifests
            solution_output_dir: Directory containing solution outputs

        Returns:
            Tuple of (individual evaluations, aggregate metrics)
        """
        evaluations = []
        aggregate = EvaluationMetrics()

        for gt_path in sorted(ground_truth_dir.glob("*.json")):
            note_id = gt_path.stem
            output_path = solution_output_dir / f"{note_id}.json"

            if not output_path.exists():
                print(f"Warning: No solution output found for {note_id}")
                continue

            eval_result = self.evaluate_from_files(gt_path, output_path, note_id)
            evaluations.append(eval_result)

            # Aggregate metrics
            aggregate.true_positives += eval_result.overall_metrics.true_positives
            aggregate.false_positives += eval_result.overall_metrics.false_positives
            aggregate.false_negatives += eval_result.overall_metrics.false_negatives

        return evaluations, aggregate

    def print_evaluation_report(
        self,
        evaluations: List[NoteEvaluation],
        aggregate: EvaluationMetrics
    ):
        """Print a formatted evaluation report."""
        print("\n" + "=" * 80)
        print("DE-IDENTIFICATION EVALUATION REPORT")
        print("=" * 80)

        # Per-note summary
        print("\nPER-NOTE RESULTS:")
        print("-" * 80)
        print(f"{'Note ID':<20} {'TP':<6} {'FP':<6} {'FN':<6} {'Precision':<12} {'Recall':<12} {'F1':<10}")
        print("-" * 80)

        for eval_result in evaluations:
            m = eval_result.overall_metrics
            print(f"{eval_result.note_id:<20} {m.true_positives:<6} {m.false_positives:<6} "
                  f"{m.false_negatives:<6} {m.precision:.2%}{'':>4} {m.recall:.2%}{'':>4} {m.f1_score:.2%}")

        # Aggregate results
        print("\n" + "=" * 80)
        print("AGGREGATE RESULTS:")
        print("-" * 80)
        print(f"Total True Positives:  {aggregate.true_positives}")
        print(f"Total False Positives: {aggregate.false_positives}")
        print(f"Total False Negatives: {aggregate.false_negatives}")
        print(f"\nOverall Precision: {aggregate.precision:.2%}")
        print(f"Overall Recall:    {aggregate.recall:.2%}")
        print(f"Overall F1 Score:  {aggregate.f1_score:.2%}")
        print("=" * 80)

        # Per-type breakdown (aggregate)
        print("\nPER-TYPE BREAKDOWN (AGGREGATE):")
        print("-" * 80)

        type_metrics = {}
        for eval_result in evaluations:
            for phi_type, metrics in eval_result.metrics_by_type.items():
                if phi_type not in type_metrics:
                    type_metrics[phi_type] = EvaluationMetrics()
                type_metrics[phi_type].true_positives += metrics.true_positives
                type_metrics[phi_type].false_positives += metrics.false_positives
                type_metrics[phi_type].false_negatives += metrics.false_negatives

        print(f"{'PHI Type':<20} {'TP':<6} {'FP':<6} {'FN':<6} {'Precision':<12} {'Recall':<12} {'F1':<10}")
        print("-" * 80)
        for phi_type, m in sorted(type_metrics.items()):
            print(f"{phi_type:<20} {m.true_positives:<6} {m.false_positives:<6} "
                  f"{m.false_negatives:<6} {m.precision:.2%}{'':>4} {m.recall:.2%}{'':>4} {m.f1_score:.2%}")

    def save_evaluation_report(
        self,
        evaluations: List[NoteEvaluation],
        aggregate: EvaluationMetrics,
        output_path: Path
    ):
        """Save evaluation results to JSON file."""
        report = {
            "aggregate": aggregate.to_dict(),
            "notes": [e.to_dict() for e in evaluations]
        }

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\nEvaluation report saved to: {output_path}")
