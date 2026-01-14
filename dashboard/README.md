# PII Evaluation Dashboard

A React + FastAPI dashboard for visualizing PII de-identification evaluation results.

## Features

- **Metrics Overview**: View precision, recall, F1 scores and TP/FP/FN counts
- **Type Breakdown**: Sortable table showing metrics by entity type (NAME, DATE, ADDRESS, etc.)
- **Annotation Browser**: Scrollable list of all FP/FN annotations, clickable to jump to exact location
- **Note Viewer**: View original clinical notes with color-coded PII highlighting
  - **Green**: True Positives (correctly identified)
  - **Yellow**: False Positives (incorrectly flagged)
  - **Red**: False Negatives (missed PII)
- **Hover Tooltips**: Detailed information showing predicted vs expected types
- **Evaluation Selector**: Switch between different evaluation runs

## Quick Start

### 1. Start the Backend

```bash
cd dashboard/backend

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### 2. Start the Frontend

```bash
cd dashboard/frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

The dashboard will be available at `http://localhost:5173`

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/evaluations` | List all evaluation runs |
| `GET /api/evaluations/{id}` | Get full evaluation data |
| `GET /api/evaluations/{id}/mistakes` | Get all mistakes for an eval |
| `GET /api/notes` | List all available notes |
| `GET /api/notes/{id}` | Get note text content |
| `GET /api/notes/{id}/annotations` | Get computed TP/FP/FN spans |

## Project Structure

```
dashboard/
├── backend/
│   ├── main.py           # FastAPI application
│   ├── models.py         # Pydantic schemas
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/          # API client and types
│   │   ├── components/   # React components
│   │   ├── pages/        # Page components
│   │   └── App.tsx       # Main app with routing
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## Data Sources

The dashboard reads from these directories in the project root:

- `eval_results/` - Evaluation result JSON files
- `eval_results/eval_mistakes_*/` - Per-document mistake files
- `synthetic_dataset/notes/` - Original clinical note text files
- `synthetic_dataset/manifests/` - Ground truth PII annotations
- `output-json/` - Model prediction output files



