# Tooling

Generate synthetic PHI notes, run deidentification, evaluate results, and visualize in a dashboard.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js and npm (for dashboard frontend)
- AWS credentials configured (`aws configure`)

## Environment Variables (optional)

```bash
export AWS_REGION=us-east-1  # default
export BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0  # default
```

## Setup

```bash
cd tooling
uv sync
```

## Workflow

Run all commands from the `tooling/` directory.

### 1. Generate Synthetic Notes

```bash
uv run generate-notes --type emergency_dept --count 10
```

Creates notes in `data/synthetic_data/notes/` and manifests in `data/synthetic_data/manifests/`.

### 2. Run Deidentification

```bash
uv run deidentification
```

Reads from `data/synthetic_data/notes/`, writes:
- `data/output/` — raw responses
- `data/output-json/` — position data
- `data/output-text/` — redacted text

### 3. Evaluate Results

```bash
uv run evaluate-deidentification
```

Compares predictions against ground truth manifests. Writes results to `data/eval_results/`.

### 4. Start Dashboard

View precision/recall metrics, browse false positives/negatives, and compare redactions against ground truth.

**API server:**
```bash
cd dashboard/api
uv run uvicorn api.main:app --reload --port 8000
```

**Frontend:**
```bash
cd dashboard/frontend
npm install
npm run dev
```

Open http://localhost:5173
