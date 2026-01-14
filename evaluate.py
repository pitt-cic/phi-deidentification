"""Evaluation script to compare PII detection output against ground truth manifests."""

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

# Reverse mapping
REVERSE_TYPE_MAPPING = {v: k for k, v in TYPE_MAPPING.items()}


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
    
    def exact_match(self, other: "Entity") -> bool:
        """Check if this entity exactly matches another entity's position."""
        return self.start == other.start and self.end == other.end
    
    def contains(self, other: "Entity") -> bool:
        """Check if this entity fully contains another entity."""
        return self.start <= other.start and self.end >= other.end
    
    def to_dict(self) -> dict[str, Any]:
        """Convert entity to dictionary for JSON serialization."""
        return {
            "type": self.type,
            "value": self.value,
            "start": self.start,
            "end": self.end,
        }


def entities_to_char_set(entities: list[Entity]) -> set[int]:
    """Convert a list of entities to a set of character indices.
    
    Each entity's range [start, end) is converted to individual character positions.
    """
    chars = set()
    for entity in entities:
        chars.update(range(entity.start, entity.end))
    return chars


def build_char_to_entity_map(entities: list[Entity]) -> dict[int, Entity]:
    """Build a mapping from character position to the entity it belongs to."""
    char_map = {}
    for entity in entities:
        for pos in range(entity.start, entity.end):
            char_map[pos] = entity
    return char_map


@dataclass
class CharEvalResult:
    """Stores character-level evaluation results."""
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    
    # Actual character positions for mistake tracking
    fp_char_positions: set[int] = field(default_factory=set)
    fn_char_positions: set[int] = field(default_factory=set)
    
    # Ground truth entities for providing context on FN chars
    ground_truth_entities: list[Entity] = field(default_factory=list)
    
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
    
    def __add__(self, other: "CharEvalResult") -> "CharEvalResult":
        """Combine two evaluation results (aggregates counts, not positions)."""
        return CharEvalResult(
            true_positives=self.true_positives + other.true_positives,
            false_positives=self.false_positives + other.false_positives,
            false_negatives=self.false_negatives + other.false_negatives,
            # Don't aggregate positions - they're doc-specific
            fp_char_positions=set(),
            fn_char_positions=set(),
            ground_truth_entities=[],
        )


def evaluate_document_char_based(
    predictions: list[Entity],
    ground_truth: list[Entity],
) -> CharEvalResult:
    """
    Evaluate predictions against ground truth using pure character-level comparison.
    
    This approach converts entity spans to sets of character indices and compares:
    - TP (true positives): characters flagged by both prediction and ground truth
    - FP (false positives): characters flagged by prediction but not in ground truth
    - FN (false negatives): characters in ground truth but not flagged by prediction
    
    No entity matching or type comparison - purely character overlap.
    
    Args:
        predictions: List of predicted entities
        ground_truth: List of ground truth entities
        
    Returns:
        CharEvalResult with character-level metrics and positions
    """
    pred_chars = entities_to_char_set(predictions)
    gt_chars = entities_to_char_set(ground_truth)
    
    tp_chars = pred_chars & gt_chars      # Characters in both
    fp_chars = pred_chars - gt_chars      # Predicted but not in ground truth
    fn_chars = gt_chars - pred_chars      # In ground truth but not predicted
    
    return CharEvalResult(
        true_positives=len(tp_chars),
        false_positives=len(fp_chars),
        false_negatives=len(fn_chars),
        fp_char_positions=fp_chars,
        fn_char_positions=fn_chars,
        ground_truth_entities=ground_truth,
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


def evaluate_document(
    predictions: list[Entity],
    ground_truth: list[Entity],
) -> CharEvalResult:
    """
    Evaluate predictions against ground truth for a single document.
    
    Uses character-based evaluation: each character position is classified as
    TP (in both prediction and ground truth), FP (only in prediction), or
    FN (only in ground truth).
    
    Args:
        predictions: List of predicted entities
        ground_truth: List of ground truth entities
        
    Returns:
        CharEvalResult with character-level metrics
    """
    return evaluate_document_char_based(predictions, ground_truth)


def evaluate_by_type_char_based(
    predictions: list[Entity],
    ground_truth: list[Entity],
) -> dict[str, CharEvalResult]:
    """Evaluate predictions by entity type using character-based comparison."""
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
        results[entity_type] = evaluate_document_char_based(type_preds, type_gt)
    
    return results


def evaluate_by_type(
    predictions: list[Entity],
    ground_truth: list[Entity],
) -> dict[str, CharEvalResult]:
    """Evaluate predictions by entity type using character-based comparison.
    
    Groups entities by type and computes character-level metrics for each type.
    
    Args:
        predictions: List of predicted entities
        ground_truth: List of ground truth entities
        
    Returns:
        Dictionary mapping entity type to CharEvalResult
    """
    return evaluate_by_type_char_based(predictions, ground_truth)


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
) -> tuple[dict[str, Any], dict[str, CharEvalResult], Path | None]:
    """
    Run character-based evaluation on all matching file pairs.
    
    Args:
        predictions_dir: Directory containing prediction JSON files
        manifests_dir: Directory containing ground truth manifest files
        texts_dir: Directory containing original text files (for mistake reports)
        verbose: Whether to print per-file results
    
    Returns:
        Tuple of:
        - Dictionary with aggregate metrics and per-file results
        - Dictionary mapping doc_id to CharEvalResult (for mistake tracking)
        - Path to texts directory (for reading original text in mistake files)
    """
    file_pairs = find_matching_files(predictions_dir, manifests_dir)
    
    if not file_pairs:
        raise ValueError(f"No matching file pairs found between {predictions_dir} and {manifests_dir}")
    
    logger.info("Found %d file pairs to evaluate", len(file_pairs))
    
    aggregate_result = CharEvalResult()
    aggregate_by_type: dict[str, CharEvalResult] = defaultdict(CharEvalResult)
    per_file_results = {}
    per_file_eval_results: dict[str, CharEvalResult] = {}
    
    for pred_path, manifest_path in file_pairs:
        predictions = load_predictions(pred_path)
        ground_truth = load_ground_truth(manifest_path)
        
        # Extract doc_id from prediction path (e.g., DI_000001 from DI_000001_positions)
        stem = pred_path.stem
        doc_id = stem[:-10] if stem.endswith("_positions") else stem
        
        # Overall evaluation (character-based)
        file_result = evaluate_document(predictions, ground_truth)
        aggregate_result = aggregate_result + file_result
        
        # Store full result for mistake tracking
        per_file_eval_results[doc_id] = file_result
        
        # Per-type evaluation (character-based)
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
            "evaluation_mode": "character_based",
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
    print("PII DETECTION EVALUATION RESULTS (Character-Based)")
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
    print(f"  True Positives:  {agg['true_positives']}")
    print(f"  False Positives: {agg['false_positives']}")
    print(f"  False Negatives: {agg['false_negatives']}")
    
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
        description="Evaluate PII detection output against ground truth manifests using character-based metrics.",
    )
    parser.add_argument(
        "--predictions-dir",
        type=Path,
        default=Path("output-json"),
        help="Directory containing prediction JSON files (default: output-json)",
    )
    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=Path("synthetic_dataset/manifests"),
        help="Directory containing ground truth manifest files (default: synthetic_dataset/manifests)",
    )
    parser.add_argument(
        "--texts-dir",
        type=Path,
        default=Path("synthetic_dataset/notes"),
        help="Directory containing original text files for character lookup (default: synthetic_dataset/notes)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print per-file results",
    )
    return parser.parse_args()


# Trivial FP values to ignore (whitespace, punctuation-only)
TRIVIAL_FP_VALUES = {" ", ", ", ",", "  ", ", ,", " ,"}


def is_trivial_fp(chars: str) -> bool:
    """Check if a false positive is trivial (just whitespace/punctuation)."""
    if not chars:
        return False
    return chars in TRIVIAL_FP_VALUES or chars.strip() == "" or chars.strip(",").strip() == ""


def group_consecutive_positions(positions: set[int]) -> list[tuple[int, int]]:
    """Group consecutive character positions into ranges.
    
    Returns list of (start, end) tuples where end is exclusive.
    Example: {1, 2, 3, 7, 8} -> [(1, 4), (7, 9)]
    """
    if not positions:
        return []
    
    sorted_pos = sorted(positions)
    groups = []
    start = sorted_pos[0]
    end = start + 1
    
    for pos in sorted_pos[1:]:
        if pos == end:  # Consecutive
            end = pos + 1
        else:  # Gap found, start new group
            groups.append((start, end))
            start = pos
            end = pos + 1
    
    groups.append((start, end))  # Don't forget the last group
    return groups


def save_per_document_mistakes(
    per_file_eval_results: dict[str, CharEvalResult],
    mistakes_dir: Path,
    texts_dir: Path | None = None,
) -> None:
    """Save per-document JSON files with character-level FP and FN details.
    
    Consecutive characters are grouped together. Each entry shows:
    - start/end: character range (end is exclusive)
    - chars: the actual characters in that range
    - manifest_context: (for FN only) the full entity value from the manifest
    """
    mistakes_dir.mkdir(parents=True, exist_ok=True)
    
    for doc_id, eval_result in per_file_eval_results.items():
        # Skip if no potential mistakes
        if not eval_result.fp_char_positions and not eval_result.fn_char_positions:
            continue
        
        # Try to load the original text to get actual characters
        text_content = None
        if texts_dir:
            text_path = texts_dir / f"{doc_id}.txt"
            if text_path.exists():
                text_content = text_path.read_text(encoding="utf-8")
        
        # Build char-to-entity map for FN context
        char_to_entity = build_char_to_entity_map(eval_result.ground_truth_entities)
        
        # Build FN entries - group consecutive positions
        fn_entries = []
        for start, end in group_consecutive_positions(eval_result.fn_char_positions):
            entry: dict[str, Any] = {"start": start, "end": end}
            if text_content:
                entry["chars"] = text_content[start:end]
            # Get manifest context from the first character's entity
            entity = char_to_entity.get(start)
            if entity:
                entry["manifest_context"] = entity.value
                entry["manifest_type"] = entity.type
            fn_entries.append(entry)
        
        # Build FP entries - group consecutive positions, filtering out trivial ones
        fp_entries = []
        filtered_fp_char_count = 0
        for start, end in group_consecutive_positions(eval_result.fp_char_positions):
            chars = text_content[start:end] if text_content else None
            # Skip trivial FPs (whitespace, punctuation only)
            if chars and is_trivial_fp(chars):
                filtered_fp_char_count += (end - start)
                continue
            entry = {"start": start, "end": end}
            if chars:
                entry["chars"] = chars
            fp_entries.append(entry)
        
        actual_fp_count = len(eval_result.fp_char_positions) - filtered_fp_char_count
        
        # Skip if no real mistakes after filtering
        if not fn_entries and not fp_entries:
            continue
        
        doc_mistakes = {
            "doc_id": doc_id,
            "evaluation_mode": "character_based",
            "summary": {
                "false_positive_count": actual_fp_count,
                "false_negative_count": len(eval_result.fn_char_positions),
                "filtered_trivial_fp_chars": filtered_fp_char_count,
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
    eval_results_dir = Path("eval_results")
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

