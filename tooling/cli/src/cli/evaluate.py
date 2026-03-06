"""Evaluation script to compare PHI detection output against ground truth manifests."""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("pii_deidentification.evaluate")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

# Mapping from prediction types (agent output) to ground truth manifest types
TYPE_MAPPING = {
    "person_name": "NAME",
    "date": "DATE",
    "phone_number": "PHONE",
    "fax_number": "FAX",
    "email": "EMAIL",
    "postal_address": "ADDRESS",
    "ssn": "SSN",
    "medical_record_number": "MRN",
    "health_plan_beneficiary_number": "HEALTH_PLAN_ID",
    "account_number": "ACCOUNT_NUMBER",
    "certificate_or_license_number": "LICENSE",
    "vehicle_identifier": "VEHICLE_ID",
    "device_identifier": "DEVICE_ID",
    "url": "URL",
    "ip_address": "IP_ADDRESS",
    "biometric_identifier": "BIOMETRIC_ID",
    "photographic_image": "PHOTO",
    "other": "OTHER",
}


@dataclass
class Entity:
    """Represents a PII/PHI entity with position information."""
    type: str
    value: str
    start: int
    end: int
    
    def overlaps(self, other: "Entity") -> bool:
        """Check if this entity overlaps with another entity."""
        return self.start < other.end and other.start < self.end


@dataclass
class EvalResult:
    """Stores entity/span-based evaluation results."""
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    
    # Actual entity spans for mistake tracking
    fp_entities: list[Entity] = field(default_factory=list)
    fn_entities: list[Entity] = field(default_factory=list)
    
    @property
    def precision(self) -> float:
        """Calculate precision: TP / (TP + FP)."""
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total > 0 else 0.0
    
    @property
    def recall(self) -> float:
        """Calculate recall: TP / (TP + FN)."""
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total > 0 else 0.0
    
    @property
    def f1(self) -> float:
        """Calculate F1 score: 2 * (precision * recall) / (precision + recall)."""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    
    def __add__(self, other: "EvalResult") -> "EvalResult":
        """Combine two evaluation results (aggregates counts, not entity lists)."""
        return EvalResult(
            true_positives=self.true_positives + other.true_positives,
            false_positives=self.false_positives + other.false_positives,
            false_negatives=self.false_negatives + other.false_negatives,
            # Don't aggregate entity lists - they're doc-specific
            fp_entities=[],
            fn_entities=[],
        )


def normalize_type(entity_type: str, is_prediction: bool = True) -> str:
    """Normalize entity type to a common format for comparison."""
    if is_prediction:
        # Convert prediction type to manifest type
        return TYPE_MAPPING.get(entity_type.lower(), entity_type.upper())
    else:
        # Already in manifest format, just uppercase
        return entity_type.upper()


def load_predictions(json_path: Path) -> list[Entity]:
    """Load prediction entities from output JSON file."""
    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)
    
    entities = []
    for item in data.get("pii_entities", []):
        entities.append(Entity(
            type=normalize_type(item["type"], is_prediction=True),
            value=item["value"],
            start=item["start"],
            end=item["end"],
        ))
    return entities


def load_ground_truth(json_path: Path) -> list[Entity]:
    """Load ground truth entities from manifest JSON file."""
    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)
    
    entities = []
    for item in data.get("phi_entities", []):
        entities.append(Entity(
            type=normalize_type(item["type"], is_prediction=False),
            value=item["value"],
            start=item["start"],
            end=item["end"],
        ))
    return entities


def evaluate_document_entity_based(
    predictions: list[Entity],
    ground_truth: list[Entity],
) -> EvalResult:
    """
    Evaluate predictions against ground truth using entity/span-level comparison.
    
    Matching criteria: Any overlap between prediction and ground truth spans.
    
    - TP (true positives): GT entities that have at least one overlapping prediction
    - FN (false negatives): GT entities with no overlapping prediction
    - FP (false positives): Prediction entities that don't overlap any GT entity
    
    Args:
        predictions: List of predicted entities
        ground_truth: List of ground truth entities
        
    Returns:
        EvalResult with entity-level metrics
    """
    # Track which predictions matched at least one GT entity
    matched_predictions: set[int] = set()
    
    tp_count = 0
    fn_entities: list[Entity] = []
    
    # For each ground truth entity, check if any prediction overlaps
    for gt in ground_truth:
        found_match = False
        for pred_idx, pred in enumerate(predictions):
            if gt.overlaps(pred):
                found_match = True
                matched_predictions.add(pred_idx)
                # Don't break - a GT entity might overlap multiple predictions
        
        if found_match:
            tp_count += 1
        else:
            fn_entities.append(gt)
    
    # FP = predictions that didn't match any GT entity
    fp_entities = [pred for idx, pred in enumerate(predictions) if idx not in matched_predictions]
    
    return EvalResult(
        true_positives=tp_count,
        false_positives=len(fp_entities),
        false_negatives=len(fn_entities),
        fp_entities=fp_entities,
        fn_entities=fn_entities,
    )


def evaluate_document(
    predictions: list[Entity],
    ground_truth: list[Entity],
) -> EvalResult:
    """
    Evaluate predictions against ground truth for a single document.
    
    Uses entity-based evaluation: each entity span is classified as
    TP (overlaps with GT), FP (no overlap with any GT), or
    FN (GT entity with no overlapping prediction).
    
    Args:
        predictions: List of predicted entities
        ground_truth: List of ground truth entities
        
    Returns:
        EvalResult with entity-level metrics
    """
    return evaluate_document_entity_based(predictions, ground_truth)


def evaluate_by_type(
    predictions: list[Entity],
    ground_truth: list[Entity],
) -> dict[str, EvalResult]:
    """
    Evaluate predictions by entity type using entity-based comparison.
    
    Groups entities by type and computes entity-level metrics for each type.
    
    Args:
        predictions: List of predicted entities
        ground_truth: List of ground truth entities
        
    Returns:
        Dictionary mapping entity type to EvalResult
    """
    # Group by type
    pred_by_type: dict[str, list[Entity]] = defaultdict(list)
    gt_by_type: dict[str, list[Entity]] = defaultdict(list)
    
    for pred in predictions:
        pred_by_type[pred.type].append(pred)
    for gt in ground_truth:
        gt_by_type[gt.type].append(gt)
    
    # Get all types
    all_types = set(pred_by_type.keys()) | set(gt_by_type.keys())
    
    results = {}
    for entity_type in sorted(all_types):
        type_preds = pred_by_type.get(entity_type, [])
        type_gt = gt_by_type.get(entity_type, [])
        results[entity_type] = evaluate_document_entity_based(type_preds, type_gt)
    
    return results


def find_matching_files(
    predictions_dir: Path,
    manifests_dir: Path,
) -> list[tuple[Path, Path]]:
    """Find matching prediction and manifest file pairs."""
    pairs = []
    
    for pred_path in sorted(predictions_dir.glob("*_positions.json")):
        # Extract the base ID (e.g., DI_000001 from DI_000001_positions.json)
        stem = pred_path.stem
        if stem.endswith("_positions"):
            base_id = stem[:-10]  # Remove "_positions"
        else:
            base_id = stem
        
        # Look for corresponding manifest
        manifest_path = manifests_dir / f"{base_id}.json"
        if manifest_path.exists():
            pairs.append((pred_path, manifest_path))
        else:
            logger.warning("No manifest found for %s", pred_path.name)
    
    return pairs


def run_evaluation(
    predictions_dir: Path,
    manifests_dir: Path,
    texts_dir: Path | None = None,
    verbose: bool = False,
) -> tuple[dict[str, Any], dict[str, EvalResult], Path | None]:
    """
    Run entity-based evaluation on all matching file pairs.
    
    Args:
        predictions_dir: Directory containing prediction JSON files
        manifests_dir: Directory containing ground truth manifest files
        texts_dir: Directory containing original text files (for mistake reports)
        verbose: Whether to print per-file results
    
    Returns:
        Tuple of:
        - Dictionary with aggregate metrics and per-file results
        - Dictionary mapping doc_id to EvalResult (for mistake tracking)
        - Path to texts directory (for reading original text in mistake files)
    """
    file_pairs = find_matching_files(predictions_dir, manifests_dir)
    
    if not file_pairs:
        raise ValueError(f"No matching file pairs found between {predictions_dir} and {manifests_dir}")
    
    logger.info("Found %d file pairs to evaluate", len(file_pairs))
    
    aggregate_result = EvalResult()
    aggregate_by_type: dict[str, EvalResult] = defaultdict(EvalResult)
    per_file_results = {}
    per_file_eval_results: dict[str, EvalResult] = {}
    
    for pred_path, manifest_path in file_pairs:
        predictions = load_predictions(pred_path)
        ground_truth = load_ground_truth(manifest_path)
        
        # Filter out trivial predictions (whitespace/punctuation) before evaluation
        predictions = filter_trivial_predictions(predictions)
        
        # Extract doc_id from prediction path (e.g., DI_000001 from DI_000001_positions)
        stem = pred_path.stem
        doc_id = stem[:-10] if stem.endswith("_positions") else stem
        
        # Overall evaluation (entity-based)
        file_result = evaluate_document(predictions, ground_truth)
        aggregate_result = aggregate_result + file_result
        
        # Store full result for mistake tracking
        per_file_eval_results[doc_id] = file_result
        
        # Per-type evaluation (entity-based)
        type_results = evaluate_by_type(predictions, ground_truth)
        for entity_type, result in type_results.items():
            aggregate_by_type[entity_type] = aggregate_by_type[entity_type] + result
        
        per_file_results[pred_path.stem] = {
            "precision": file_result.precision,
            "recall": file_result.recall,
            "f1": file_result.f1,
            "true_positives": file_result.true_positives,
            "false_positives": file_result.false_positives,
            "false_negatives": file_result.false_negatives,
        }
        
        if verbose:
            logger.info(
                "%s: P=%.3f R=%.3f F1=%.3f (TP=%d FP=%d FN=%d)",
                pred_path.stem,
                file_result.precision,
                file_result.recall,
                file_result.f1,
                file_result.true_positives,
                file_result.false_positives,
                file_result.false_negatives,
            )
    
    # Build results dictionary
    results = {
        "settings": {
            "evaluation_mode": "entity_based",
            "predictions_dir": str(predictions_dir),
            "manifests_dir": str(manifests_dir),
            "num_files": len(file_pairs),
        },
        "aggregate": {
            "precision": aggregate_result.precision,
            "recall": aggregate_result.recall,
            "f1": aggregate_result.f1,
            "true_positives": aggregate_result.true_positives,
            "false_positives": aggregate_result.false_positives,
            "false_negatives": aggregate_result.false_negatives,
        },
        "by_type": {
            entity_type: {
                "precision": result.precision,
                "recall": result.recall,
                "f1": result.f1,
                "true_positives": result.true_positives,
                "false_positives": result.false_positives,
                "false_negatives": result.false_negatives,
            }
            for entity_type, result in sorted(aggregate_by_type.items())
        },
        "per_file": per_file_results,
    }
    
    return results, per_file_eval_results, texts_dir


def print_results(results: dict[str, Any]) -> None:
    """Print evaluation results in a formatted way."""
    print("\n" + "=" * 70)
    print("PHI DETECTION EVALUATION RESULTS (Entity-Based)")
    print("=" * 70)
    
    settings = results["settings"]
    print(f"\nSettings:")
    print(f"  Files evaluated: {settings['num_files']}")
    
    agg = results["aggregate"]
    print(f"\n{'AGGREGATE METRICS':^70}")
    print("-" * 70)
    print(f"  Precision: {agg['precision']:.4f}")
    print(f"  Recall:    {agg['recall']:.4f}")
    print(f"  F1 Score:  {agg['f1']:.4f}")
    print(f"  True Positives:  {agg['true_positives']} entities")
    print(f"  False Positives: {agg['false_positives']} entities")
    print(f"  False Negatives: {agg['false_negatives']} entities")
    
    print(f"\n{'METRICS BY ENTITY TYPE':^70}")
    print("-" * 70)
    print(f"{'Type':<25} {'Precision':>10} {'Recall':>10} {'F1':>10} {'TP':>6} {'FP':>6} {'FN':>6}")
    print("-" * 70)
    
    for entity_type, metrics in results["by_type"].items():
        print(
            f"{entity_type:<25} "
            f"{metrics['precision']:>10.4f} "
            f"{metrics['recall']:>10.4f} "
            f"{metrics['f1']:>10.4f} "
            f"{metrics['true_positives']:>6} "
            f"{metrics['false_positives']:>6} "
            f"{metrics['false_negatives']:>6}"
        )
    
    print("=" * 70)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate PHI detection output against ground truth manifests using entity-based metrics.",
    )
    parser.add_argument(
        "--predictions-dir",
        type=Path,
        default=Path("data/output-json"),
        help="Directory containing prediction JSON files (default: data/output-json)",
    )
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=Path("data/synthetic_data/manifests"),
        help="Directory containing ground truth manifest files (default: data/synthetic_data/manifests)",
    )
    parser.add_argument(
        "--texts-dir",
        type=Path,
        default=Path("data/synthetic_data/notes"),
        help="Directory containing original text files for character lookup (default: data/synthetic_data/notes)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print per-file results",
    )
    return parser.parse_args()


# Trivial entity values to ignore (whitespace, punctuation-only)
TRIVIAL_VALUES = {" ", ", ", ",", "  ", ", ,", " ,"}


def is_trivial_entity(value: str) -> bool:
    """Check if an entity is trivial (just whitespace/punctuation)."""
    if not value:
        return False
    return value in TRIVIAL_VALUES or value.strip() == "" or value.strip(",").strip() == ""


def filter_trivial_predictions(predictions: list[Entity]) -> list[Entity]:
    """Filter out trivial predictions (whitespace/punctuation only) before evaluation."""
    return [p for p in predictions if not is_trivial_entity(p.value)]


def save_per_document_mistakes(
    per_file_eval_results: dict[str, EvalResult],
    mistakes_dir: Path,
    texts_dir: Path | None = None,
) -> None:
    """Save per-document JSON files with entity-level FP and FN details.
    
    Each entry shows:
    - start/end: character range (end is exclusive)
    - chars: the actual text value of the entity
    - type: the entity type
    - manifest_context: (for FN only) the full entity value from the manifest
    """
    mistakes_dir.mkdir(parents=True, exist_ok=True)
    
    for doc_id, eval_result in per_file_eval_results.items():
        # Skip if no mistakes
        if not eval_result.fp_entities and not eval_result.fn_entities:
            continue
        
        # Try to load the original text to get actual characters (backup if value is missing)
        text_content = None
        if texts_dir:
            text_path = texts_dir / f"{doc_id}.txt"
            if text_path.exists():
                text_content = text_path.read_text(encoding="utf-8")
        
        # Build FN entries
        fn_entries = []
        for entity in eval_result.fn_entities:
            chars = entity.value
            if not chars and text_content:
                chars = text_content[entity.start:entity.end]
            entry: dict[str, Any] = {
                "start": entity.start,
                "end": entity.end,
                "chars": chars,
                "manifest_context": entity.value,
                "manifest_type": entity.type,
            }
            fn_entries.append(entry)
        
        # Build FP entries (trivial predictions already filtered before evaluation)
        fp_entries = []
        for entity in eval_result.fp_entities:
            chars = entity.value
            if not chars and text_content:
                chars = text_content[entity.start:entity.end]
            entry = {
                "start": entity.start,
                "end": entity.end,
                "chars": chars,
                "type": entity.type,
            }
            fp_entries.append(entry)
        
        # Skip if no mistakes
        if not fn_entries and not fp_entries:
            continue
        
        doc_mistakes = {
            "doc_id": doc_id,
            "evaluation_mode": "entity_based",
            "summary": {
                "false_positive_count": len(fp_entries),
                "false_negative_count": len(fn_entries),
            },
            "false_negatives": fn_entries,
            "false_positives": fp_entries,
        }
        
        output_path = mistakes_dir / f"{doc_id}.json"
        output_path.write_text(json.dumps(doc_mistakes, indent=2), encoding="utf-8")
    
    logger.info("Per-document mistakes saved to %s/ (%d files)", mistakes_dir, len(list(mistakes_dir.glob("*.json"))))


def main() -> None:
    args = parse_args()
    
    results, per_file_eval_results, texts_dir = run_evaluation(
        predictions_dir=args.predictions_dir,
        manifests_dir=args.manifests_dir,
        texts_dir=args.texts_dir,
        verbose=args.verbose,
    )
    
    print_results(results)
    
    # Always save results to eval_results folder
    eval_results_dir = Path("data/eval_results")
    eval_results_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = eval_results_dir / f"eval_{timestamp}.json"
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    logger.info("Results saved to %s", output_path)
    
    # Save per-document mistake files
    mistakes_dir = eval_results_dir / f"eval_mistakes_{timestamp}"
    save_per_document_mistakes(per_file_eval_results, mistakes_dir, texts_dir)


if __name__ == "__main__":
    main()
