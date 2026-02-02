"""FastAPI backend for the PII Evaluation Dashboard."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import (
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
REDACTED_DIR = PROJECT_ROOT / "output-text"
SAFE_HARBOR_REDACTED_DIR = PROJECT_ROOT / "sample-output-text"
SAFE_HARBOR_DEID_DIR = PROJECT_ROOT / "sample_safe_harbor_notes" / "text_manifest"
SAFE_HARBOR_ORIGINAL_DIR = PROJECT_ROOT / "sample_safe_harbor_notes" / "notes"


def parse_eval_timestamp(filename: str) -> str:
    """Extract timestamp from evaluation filename."""
    match = re.search(r"eval_(\d{8}_\d{6})\.json", filename)
    if match:
        ts = match.group(1)
        return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
    return filename


@app.get("/api/evaluations", response_model=list[EvaluationSummary])
def list_evaluations():
    """List all available evaluation runs."""
    evaluations = []
    
    for eval_file in sorted(EVAL_RESULTS_DIR.glob("eval_*.json"), reverse=True):
        if eval_file.is_dir():
            continue
        if "mistakes" in eval_file.name:
            continue
            
        try:
            with eval_file.open() as f:
                data = json.load(f)
            
            eval_id = eval_file.stem
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
    mistakes_dir = EVAL_RESULTS_DIR / eval_id.replace("eval_", "eval_mistakes_")
    
    if not mistakes_dir.exists():
        return []
    
    mistakes = []
    for mistake_file in sorted(mistakes_dir.glob("*.json")):
        try:
            with mistake_file.open() as f:
                data = json.load(f)
            
            def normalize_mistake_entry(entry: dict) -> dict:
                normalized = entry.copy()
                if 'chars' not in normalized and 'value' in normalized:
                    normalized['chars'] = normalized.pop('value')
                return normalized
            
            mistakes.append(DocumentMistakes(
                doc_id=data.get("doc_id", mistake_file.stem),
                false_positive_count=data.get("summary", {}).get("false_positive_count", 0),
                false_negative_count=data.get("summary", {}).get("false_negative_count", 0),
                false_positives=[
                    MistakeEntry(**normalize_mistake_entry(fp)) for fp in data.get("false_positives", [])
                ],
                false_negatives=[
                    MistakeEntry(**normalize_mistake_entry(fn)) for fn in data.get("false_negatives", [])
                ],
            ))
        except (json.JSONDecodeError, KeyError):
            continue
    
    return mistakes


@app.get("/api/notes", response_model=list[NoteSummary])
def list_notes(eval_id: str | None = None):
    """List all available notes."""
    notes = []
    notes_with_mistakes = set()
    if eval_id:
        mistakes_dir = EVAL_RESULTS_DIR / eval_id.replace("eval_", "eval_mistakes_")
        if mistakes_dir.exists():
            for f in mistakes_dir.glob("*.json"):
                notes_with_mistakes.add(f.stem)
    
    for note_file in sorted(NOTES_DIR.glob("*.txt")):
        note_id = note_file.stem
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


@app.get("/api/notes/{note_id}/redacted", response_model=NoteContent)
def get_note_redacted(note_id: str):
    """Get redacted note text."""
    redacted_file = REDACTED_DIR / f"{note_id}_redacted.txt"

    if not redacted_file.exists():
        raise HTTPException(status_code=404, detail=f"Redacted note {note_id} not found")

    text = redacted_file.read_text(encoding="utf-8")
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
    note_file = NOTES_DIR / f"{note_id}.txt"
    if not note_file.exists():
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    text = note_file.read_text(encoding="utf-8")
    
    positions_file = POSITIONS_DIR / f"{note_id}_positions.json"
    predictions = []
    if positions_file.exists():
        with positions_file.open() as f:
            data = json.load(f)
        predictions = data.get("pii_entities", [])
    
    manifest_file = MANIFESTS_DIR / f"{note_id}.json"
    ground_truth = []
    if manifest_file.exists():
        with manifest_file.open() as f:
            data = json.load(f)
        ground_truth = data.get("phi_entities", [])
    
    pred_chars: dict[int, dict] = {}
    gt_chars: dict[int, dict] = {}
    
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
    
    all_positions = set(pred_chars.keys()) | set(gt_chars.keys())
    spans: list[AnnotationSpan] = []
    
    if not all_positions:
        return NoteAnnotations(note_id=note_id, spans=[])
    
    sorted_positions = sorted(all_positions)
    
    def get_classification(pos: int) -> tuple[str, str | None, str | None]:
        in_pred = pos in pred_chars
        in_gt = pos in gt_chars
        
        if in_pred and in_gt:
            return "tp", pred_chars[pos]["type"], gt_chars[pos]["type"]
        elif in_pred:
            return "fp", pred_chars[pos]["type"], None
        else:
            return "fn", None, gt_chars[pos]["type"]
    
    current_start = sorted_positions[0]
    current_class, current_pred_type, current_exp_type = get_classification(current_start)
    
    for i, pos in enumerate(sorted_positions[1:], 1):
        cls, pred_type, exp_type = get_classification(pos)
        prev_pos = sorted_positions[i - 1]
        is_consecutive = pos == prev_pos + 1
        same_classification = cls == current_class
        
        if not is_consecutive or not same_classification:
            end_pos = prev_pos + 1
            spans.append(AnnotationSpan(
                start=current_start,
                end=end_pos,
                text=text[current_start:end_pos],
                classification=current_class,
                predicted_type=current_pred_type,
                expected_type=current_exp_type,
            ))
            current_start = pos
            current_class = cls
            current_pred_type = pred_type
            current_exp_type = exp_type
    
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


@app.get("/api/safe-harbor/notes", response_model=list[NoteSummary])
def list_safe_harbor_notes():
    """List all available Safe Harbor Notes (only those with all 3 files)."""
    notes = []
    
    if not SAFE_HARBOR_REDACTED_DIR.exists():
        return notes
    
    for redacted_file in sorted(SAFE_HARBOR_REDACTED_DIR.glob("*_redacted.txt")):
        note_id = redacted_file.stem.replace("_redacted", "")
        original_file = SAFE_HARBOR_ORIGINAL_DIR / f"{note_id}.txt"
        deid_file = SAFE_HARBOR_DEID_DIR / f"{note_id}.DEID"
        
        # Only list notes where all three files exist
        if not original_file.exists() or not deid_file.exists():
            continue
        
        notes.append(NoteSummary(
            note_id=note_id,
            note_type=None,
            has_mistakes=True,  # All listed notes have ground truth
        ))
    
    return notes


@app.get("/api/safe-harbor/notes/{note_id}/comparison")
def get_safe_harbor_comparison(note_id: str):
    """Compare original, redacted (LLM), and DEID (ground truth) texts."""
    original_file = SAFE_HARBOR_ORIGINAL_DIR / f"{note_id}.txt"
    redacted_file = SAFE_HARBOR_REDACTED_DIR / f"{note_id}_redacted.txt"
    deid_file = SAFE_HARBOR_DEID_DIR / f"{note_id}.DEID"
    
    if not original_file.exists():
        raise HTTPException(status_code=404, detail=f"Original file {note_id} not found")
    
    if not redacted_file.exists():
        raise HTTPException(status_code=404, detail=f"Redacted file {note_id} not found")
    
    if not deid_file.exists():
        raise HTTPException(status_code=404, detail=f"DEID file {note_id} not found")
    
    def load_with_encoding(path: Path) -> str:
        raw_bytes = path.read_bytes()
        if len(raw_bytes) >= 2:
            if raw_bytes[:2] == b'\xff\xfe':
                return raw_bytes.decode('utf-16-le')
            elif raw_bytes[:2] == b'\xfe\xff':
                return raw_bytes.decode('utf-16-be')
        try:
            return raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return raw_bytes.decode('utf-16-le')
            except UnicodeDecodeError:
                return raw_bytes.decode('latin-1', errors='replace')
    
    original_text = load_with_encoding(original_file).replace('\r\n', '\n').replace('\r', '\n')
    redacted_text = load_with_encoding(redacted_file).replace('\r\n', '\n').replace('\r', '\n')
    deid_text = load_with_encoding(deid_file).replace('\r\n', '\n').replace('\r', '\n')
    
    return {
        "note_id": note_id,
        "original_text": original_text,
        "redacted_text": redacted_text,
        "deid_text": deid_text
    }


@app.get("/api/safe-harbor/metrics")
def get_safe_harbor_metrics():
    """Get aggregate metrics for all Safe Harbor Notes."""
    if not SAFE_HARBOR_REDACTED_DIR.exists():
        return {
            "total_files": 0,
        }
    
    total_files = 0
    
    for redacted_file in sorted(SAFE_HARBOR_REDACTED_DIR.glob("*_redacted.txt")):
        note_id = redacted_file.stem.replace("_redacted", "")
        deid_file = SAFE_HARBOR_DEID_DIR / f"{note_id}.DEID"
        
        if deid_file.exists():
            total_files += 1
    
    return {
        "total_files": total_files,
    }


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)