"""FastAPI backend for the PII Evaluation Dashboard."""

from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from dashboard.backend.models import (
    EvaluationSummary,
    EvaluationDetail,
    MetricsSummary,
    TypeMetrics,
    FileMetrics,
    DocumentMistakes,
    MistakeEntry,
    NoteSummary,
    NoteContent,
    NoteAnnotations,
    AnnotationSpan,
)

app = FastAPI(title="PII Evaluation Dashboard API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data directories (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent
EVAL_RESULTS_DIR = PROJECT_ROOT / "eval_results"
NOTES_DIR = PROJECT_ROOT / "synthetic_dataset" / "notes"
MANIFESTS_DIR = PROJECT_ROOT / "synthetic_dataset" / "manifests"
POSITIONS_DIR = PROJECT_ROOT / "output-json"


def parse_eval_timestamp(filename: str) -> str:
    """Extract timestamp from evaluation filename."""
    # eval_20251215_231512.json -> 20251215_231512
    match = re.search(r"eval_(\d{8}_\d{6})\.json", filename)
    if match:
        ts = match.group(1)
        # Format nicely: 2025-12-15 23:15:12
        return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
    return filename


@app.get("/api/evaluations", response_model=list[EvaluationSummary])
def list_evaluations():
    """List all available evaluation runs."""
    evaluations = []
    
    for eval_file in sorted(EVAL_RESULTS_DIR.glob("eval_*.json"), reverse=True):
        # Skip mistake directories
        if eval_file.is_dir():
            continue
        if "mistakes" in eval_file.name:
            continue
            
        try:
            with eval_file.open() as f:
                data = json.load(f)
            
            eval_id = eval_file.stem  # e.g., eval_20251215_231512
            evaluations.append(EvaluationSummary(
                eval_id=eval_id,
                timestamp=parse_eval_timestamp(eval_file.name),
                num_files=data.get("settings", {}).get("num_files", 0),
                precision=data.get("aggregate", {}).get("precision", 0),
                recall=data.get("aggregate", {}).get("recall", 0),
                f1=data.get("aggregate", {}).get("f1", 0),
            ))
        except (json.JSONDecodeError, KeyError):
            continue
    
    return evaluations


@app.get("/api/evaluations/{eval_id}", response_model=EvaluationDetail)
def get_evaluation(eval_id: str):
    """Get full evaluation data."""
    eval_file = EVAL_RESULTS_DIR / f"{eval_id}.json"
    
    if not eval_file.exists():
        raise HTTPException(status_code=404, detail=f"Evaluation {eval_id} not found")
    
    with eval_file.open() as f:
        data = json.load(f)
    
    agg = data.get("aggregate", {})
    by_type = [
        TypeMetrics(
            type_name=type_name,
            precision=metrics.get("precision", 0),
            recall=metrics.get("recall", 0),
            f1=metrics.get("f1", 0),
            true_positives=metrics.get("true_positives", 0),
            false_positives=metrics.get("false_positives", 0),
            false_negatives=metrics.get("false_negatives", 0),
        )
        for type_name, metrics in data.get("by_type", {}).items()
    ]
    
    per_file = [
        FileMetrics(
            file_id=file_id.replace("_positions", ""),
            precision=metrics.get("precision", 0),
            recall=metrics.get("recall", 0),
            f1=metrics.get("f1", 0),
            true_positives=metrics.get("true_positives", 0),
            false_positives=metrics.get("false_positives", 0),
            false_negatives=metrics.get("false_negatives", 0),
        )
        for file_id, metrics in data.get("per_file", {}).items()
    ]
    
    return EvaluationDetail(
        eval_id=eval_id,
        settings=data.get("settings", {}),
        aggregate=MetricsSummary(
            precision=agg.get("precision", 0),
            recall=agg.get("recall", 0),
            f1=agg.get("f1", 0),
            true_positives=agg.get("true_positives", 0),
            false_positives=agg.get("false_positives", 0),
            false_negatives=agg.get("false_negatives", 0),
        ),
        by_type=by_type,
        per_file=per_file,
    )


@app.get("/api/evaluations/{eval_id}/mistakes", response_model=list[DocumentMistakes])
def get_evaluation_mistakes(eval_id: str):
    """Get all mistake files for an evaluation."""
    # eval_20251215_231512 -> eval_mistakes_20251215_231512
    mistakes_dir = EVAL_RESULTS_DIR / eval_id.replace("eval_", "eval_mistakes_")
    
    if not mistakes_dir.exists():
        return []
    
    mistakes = []
    for mistake_file in sorted(mistakes_dir.glob("*.json")):
        try:
            with mistake_file.open() as f:
                data = json.load(f)
            
            mistakes.append(DocumentMistakes(
                doc_id=data.get("doc_id", mistake_file.stem),
                false_positive_count=data.get("summary", {}).get("false_positive_count", 0),
                false_negative_count=data.get("summary", {}).get("false_negative_count", 0),
                false_positives=[
                    MistakeEntry(**fp) for fp in data.get("false_positives", [])
                ],
                false_negatives=[
                    MistakeEntry(**fn) for fn in data.get("false_negatives", [])
                ],
            ))
        except (json.JSONDecodeError, KeyError):
            continue
    
    return mistakes


@app.get("/api/notes", response_model=list[NoteSummary])
def list_notes(eval_id: str | None = None):
    """List all available notes."""
    notes = []
    
    # Get set of notes with mistakes if eval_id provided
    notes_with_mistakes = set()
    if eval_id:
        mistakes_dir = EVAL_RESULTS_DIR / eval_id.replace("eval_", "eval_mistakes_")
        if mistakes_dir.exists():
            for f in mistakes_dir.glob("*.json"):
                notes_with_mistakes.add(f.stem)
    
    for note_file in sorted(NOTES_DIR.glob("*.txt")):
        note_id = note_file.stem
        
        # Try to get note type from manifest
        note_type = None
        manifest_file = MANIFESTS_DIR / f"{note_id}.json"
        if manifest_file.exists():
            try:
                with manifest_file.open() as f:
                    manifest = json.load(f)
                note_type = manifest.get("note_type")
            except (json.JSONDecodeError, KeyError):
                pass
        
        notes.append(NoteSummary(
            note_id=note_id,
            note_type=note_type,
            has_mistakes=note_id in notes_with_mistakes,
        ))
    
    return notes


@app.get("/api/notes/{note_id}", response_model=NoteContent)
def get_note(note_id: str):
    """Get original note text."""
    note_file = NOTES_DIR / f"{note_id}.txt"
    
    if not note_file.exists():
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    
    text = note_file.read_text(encoding="utf-8")
    return NoteContent(note_id=note_id, text=text)


# Type mapping from predictions to manifest types
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


def normalize_type(entity_type: str) -> str:
    """Normalize entity type to uppercase format."""
    return TYPE_MAPPING.get(entity_type.lower(), entity_type.upper())


@app.get("/api/notes/{note_id}/annotations", response_model=NoteAnnotations)
def get_note_annotations(note_id: str):
    """Get computed annotations (TP/FP/FN spans) for a note."""
    # Load note text
    note_file = NOTES_DIR / f"{note_id}.txt"
    if not note_file.exists():
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    text = note_file.read_text(encoding="utf-8")
    
    # Load predictions
    positions_file = POSITIONS_DIR / f"{note_id}_positions.json"
    predictions = []
    if positions_file.exists():
        with positions_file.open() as f:
            data = json.load(f)
        predictions = data.get("pii_entities", [])
    
    # Load ground truth
    manifest_file = MANIFESTS_DIR / f"{note_id}.json"
    ground_truth = []
    if manifest_file.exists():
        with manifest_file.open() as f:
            data = json.load(f)
        ground_truth = data.get("phi_entities", [])
    
    # Build character sets and maps
    pred_chars: dict[int, dict] = {}  # char_pos -> entity info
    gt_chars: dict[int, dict] = {}    # char_pos -> entity info
    
    for entity in predictions:
        for pos in range(entity["start"], entity["end"]):
            if pos not in pred_chars:
                pred_chars[pos] = {
                    "type": normalize_type(entity["type"]),
                    "value": entity["value"],
                    "start": entity["start"],
                    "end": entity["end"],
                }
    
    for entity in ground_truth:
        for pos in range(entity["start"], entity["end"]):
            if pos not in gt_chars:
                gt_chars[pos] = {
                    "type": entity["type"].upper(),
                    "value": entity["value"],
                    "start": entity["start"],
                    "end": entity["end"],
                }
    
    # Classify each character position
    all_positions = set(pred_chars.keys()) | set(gt_chars.keys())
    
    # Group consecutive positions with same classification
    spans: list[AnnotationSpan] = []
    
    if not all_positions:
        return NoteAnnotations(note_id=note_id, spans=[])
    
    sorted_positions = sorted(all_positions)
    
    def get_classification(pos: int) -> tuple[str, str | None, str | None]:
        """Get classification and types for a position."""
        in_pred = pos in pred_chars
        in_gt = pos in gt_chars
        
        if in_pred and in_gt:
            return "tp", pred_chars[pos]["type"], gt_chars[pos]["type"]
        elif in_pred:
            return "fp", pred_chars[pos]["type"], None
        else:
            return "fn", None, gt_chars[pos]["type"]
    
    # Build spans by grouping consecutive positions with same classification
    current_start = sorted_positions[0]
    current_class, current_pred_type, current_exp_type = get_classification(current_start)
    
    for i, pos in enumerate(sorted_positions[1:], 1):
        cls, pred_type, exp_type = get_classification(pos)
        
        # Check if this continues the current span (consecutive and same classification)
        prev_pos = sorted_positions[i - 1]
        is_consecutive = pos == prev_pos + 1
        same_classification = cls == current_class
        
        if not is_consecutive or not same_classification:
            # End current span
            end_pos = prev_pos + 1
            spans.append(AnnotationSpan(
                start=current_start,
                end=end_pos,
                text=text[current_start:end_pos],
                classification=current_class,
                predicted_type=current_pred_type,
                expected_type=current_exp_type,
            ))
            # Start new span
            current_start = pos
            current_class = cls
            current_pred_type = pred_type
            current_exp_type = exp_type
    
    # Don't forget the last span
    end_pos = sorted_positions[-1] + 1
    spans.append(AnnotationSpan(
        start=current_start,
        end=end_pos,
        text=text[current_start:end_pos],
        classification=current_class,
        predicted_type=current_pred_type,
        expected_type=current_exp_type,
    ))
    
    return NoteAnnotations(note_id=note_id, spans=spans)


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)



