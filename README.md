# PII De-identification Project

A PII (Personally Identifiable Information) detection and redaction system using AWS Bedrock and Claude for analyzing medical notes. Designed to identify HIPAA 18 identifiers and other sensitive information.

## Features

- **PII Detection**: Uses Claude via AWS Bedrock to detect PII in medical documents
- **Batch Processing**: Process multiple documents concurrently with configurable concurrency
- **Automatic Redaction**: Replace detected PII with type-specific tags (e.g., `[PERSON_NAME]`)
- **Evaluation Framework**: Character-level precision/recall/F1 metrics against ground truth
- **Dashboard**: React frontend with FastAPI backend for visualizing results

## Project Structure

```
├── agent/                    # PII detection agent
│   ├── agent.py              # Bedrock agent configuration
│   ├── models.py             # Pydantic models for PII entities
│   └── prompt.py             # System prompt for the agent
├── dashboard/                # Evaluation dashboard
│   ├── backend/              # FastAPI backend
│   └── frontend/             # React frontend
├── main.py                   # Main entry point for processing
├── evaluate.py               # Evaluation script
├── redact_pii.py             # PII redaction utilities
└── synthetic_dataset/        # Test data (notes, manifests, templates)
```

## Setup

### Prerequisites

- Python 3.11+
- AWS account with Bedrock access
- Node.js 18+ (for dashboard frontend)

### Installation

1. Clone the repository and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure AWS credentials:
   ```bash
   aws configure
   ```
   Or copy `.env.example` to `.env` and set your credentials.

3. (Optional) Set up Logfire for observability:
   ```bash
   # In .env
   LOGFIRE_API_KEY=your_api_key
   LOGFIRE_PROJECT=your_project
   ```

## Usage

### Process a Single Document

```bash
python main.py document.txt
```

### Process a Dataset

```bash
# Process all .txt files in synthetic_dataset/notes/
python main.py --dataset synthetic_dataset/notes --output-dir output

# With custom concurrency
python main.py --dataset synthetic_dataset/notes --concurrency 5

# Skip automatic redaction
python main.py --dataset synthetic_dataset/notes --no-redact
```

### Run Evaluation

```bash
python evaluate.py
```

Options:
- `--predictions-dir`: Directory with prediction JSON files (default: `output-json`)
- `--manifests-dir`: Directory with ground truth manifests (default: `synthetic_dataset/manifests`)
- `--verbose`: Print per-file results

### Run the Dashboard

1. Start the backend:
   ```bash
   cd dashboard/backend
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```

2. Start the frontend:
   ```bash
   cd dashboard/frontend
   npm install
   npm run dev
   ```

3. Open http://localhost:5173

## PII Types Detected

Based on HIPAA 18 identifiers:

- `person_name` - Names (full, first, last, initials, titles)
- `postal_address` - Street addresses, cities, zip codes
- `date` - Dates (birth, admission, discharge, etc.)
- `phone_number` - Phone numbers
- `fax_number` - Fax numbers
- `email` - Email addresses
- `ssn` - Social Security Numbers
- `medical_record_number` - MRNs
- `health_plan_beneficiary_number` - Health plan IDs
- `account_number` - Account numbers
- `certificate_or_license_number` - License/certificate numbers
- `vehicle_identifier` - VINs, plate numbers
- `device_identifier` - Device serial numbers
- `url` - Web URLs
- `ip_address` - IP addresses
- `biometric_identifier` - Biometric data references
- `photographic_image` - Photo references
- `other` - Facility names, gender, etc.

## Output Format

### Detection Response (`output/*.json`)

```json
{
  "source": "path/to/document.txt",
  "language": "en",
  "pii_types": ["person_name", "date", ...],
  "response": {
    "pii_entities": [
      {
        "type": "person_name",
        "value": "John Smith",
        "reason": "Patient name",
        "confidence": "high"
      }
    ],
    "summary": "Medical note with patient demographics",
    "needs_review": false
  }
}
```

### Positions File (`output-json/*_positions.json`)

```json
{
  "pii_entities": [
    {
      "type": "person_name",
      "value": "John Smith",
      "start": 45,
      "end": 55
    }
  ]
}
```

## Evaluation Metrics

The evaluation uses **character-level** metrics:

- **Precision**: Fraction of predicted characters that are actually PII
- **Recall**: Fraction of actual PII characters that were detected
- **F1 Score**: Harmonic mean of precision and recall

Results are saved to `eval_results/` with per-document mistake files for debugging.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region for Bedrock | `us-east-1` |
| `BEDROCK_MODEL_ID` | Model ID to use | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| `LOGFIRE_API_KEY` | Logfire API key (optional) | - |
| `LOGFIRE_PROJECT` | Logfire project name (optional) | - |
