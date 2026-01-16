# PII Evaluation Dashboard

React + FastAPI dashboard for visualizing PII detection results.

## Quick Start

**Backend:**
```bash
cd dashboard/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd dashboard/frontend
npm install
npm run dev
```

Open http://localhost:5173

## Features

- **Metrics Overview** — Precision, recall, F1 with TP/FP/FN counts
- **Type Breakdown** — Sortable metrics by entity type
- **Annotation Browser** — Click any FP/FN to jump to its location in the note
- **Note Viewer** — Color-coded highlighting (green=TP, yellow=FP, red=FN)
- **Safe Harbor Comparison** — Side-by-side view of LLM redactions vs ground truth

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/evaluations` | List evaluation runs |
| `GET /api/evaluations/{id}` | Get evaluation details |
| `GET /api/evaluations/{id}/mistakes` | Get FP/FN for an eval |
| `GET /api/notes` | List notes |
| `GET /api/notes/{id}` | Get note text |
| `GET /api/notes/{id}/annotations` | Get TP/FP/FN spans |
| `GET /api/safe-harbor/notes` | List Safe Harbor notes |
| `GET /api/safe-harbor/notes/{id}/comparison` | Compare redacted vs ground truth |

## Data Sources

Reads from project root:
- `eval_results/` — Evaluation JSON files
- `synthetic_dataset/notes/` — Original notes
- `synthetic_dataset/manifests/` — Ground truth
- `output-json/` — Predictions
- `sample-output-text/` — Safe Harbor redacted files

**To change these paths**, edit the constants at the top of `backend/main.py`:
```python
EVAL_RESULTS_DIR = PROJECT_ROOT / "eval_results"
NOTES_DIR = PROJECT_ROOT / "synthetic_dataset" / "notes"
POSITIONS_DIR = PROJECT_ROOT / "output-json"
# etc.
```
