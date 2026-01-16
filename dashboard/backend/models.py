"""Pydantic models for the dashboard API."""

from pydantic import BaseModel


class EvaluationSummary(BaseModel):
    """Summary of an evaluation run."""
    eval_id: str
    timestamp: str
    num_files: int
    precision: float
    recall: float
    f1: float


class MetricsSummary(BaseModel):
    """Aggregate metrics."""
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


class TypeMetrics(BaseModel):
    """Metrics for a single entity type."""
    type_name: str
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


class FileMetrics(BaseModel):
    """Metrics for a single file."""
    file_id: str
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


class EvaluationDetail(BaseModel):
    """Full evaluation data."""
    eval_id: str
    settings: dict
    aggregate: MetricsSummary
    by_type: list[TypeMetrics]
    per_file: list[FileMetrics]


class MistakeEntry(BaseModel):
    """A single FP or FN entry."""
    start: int
    end: int
    chars: str | None = None
    type: str | None = None  # Entity type (predicted for FP, expected for FN)
    manifest_context: str | None = None
    manifest_type: str | None = None


class DocumentMistakes(BaseModel):
    """Mistakes for a single document."""
    doc_id: str
    false_positive_count: int
    false_negative_count: int
    false_positives: list[MistakeEntry]
    false_negatives: list[MistakeEntry]


class NoteSummary(BaseModel):
    """Summary of a note."""
    note_id: str
    note_type: str | None = None
    has_mistakes: bool = False


class NoteContent(BaseModel):
    """Full note content."""
    note_id: str
    text: str


class AnnotationSpan(BaseModel):
    """A highlighted span in the note."""
    start: int
    end: int
    text: str
    classification: str  # "tp", "fp", "fn"
    predicted_type: str | None = None
    expected_type: str | None = None


class NoteAnnotations(BaseModel):
    """All annotations for a note."""
    note_id: str
    spans: list[AnnotationSpan]



