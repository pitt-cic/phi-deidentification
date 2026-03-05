# PII/PII Deidentification Project

Detect and redact PII/PHI from medical notes using AWS Bedrock (Claude). Identifies HIPAA 18 identifiers with entity-level evaluation metrics.

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Configure AWS
aws configure

# Process documents
python main.py --dataset synthetic_dataset/notes --output-dir output

# Evaluate results
python evaluate.py
```

## Project Structure

```
├── agent/              # Bedrock agent (prompt, models)
├── dashboard/          # React + FastAPI evaluation dashboard
├── main.py             # Process documents
├── evaluate.py         # Run evaluation
├── redact_pii.py       # Redaction utilities
└── synthetic_dataset/  # Test data
```

## Usage

**Single document:**
```bash
python main.py document.txt
```

**Batch processing:**
```bash
python main.py --dataset path/to/notes --output-dir output --concurrency 5
```

**Evaluation:**
```bash
python evaluate.py --predictions-dir output-json --manifests-dir synthetic_dataset/manifests
```

## Dashboard

```bash
# Backend
cd dashboard/backend && pip install -r requirements.txt
uvicorn main:app --reload

# Frontend  
cd dashboard/frontend && npm install && npm run dev
```

Open http://localhost:5173

## Output

Detection results go to `output/`, redacted text to `output-text/`, position data to `output-json/`. Change with `--output-dir` flag (derived dirs get `-text` and `-json` suffixes automatically).

```json
{
  "pii_entities": [
    {"type": "person_name", "value": "John Smith", "start": 45, "end": 55}
  ]
}
```

## PII Types

Detects HIPAA 18 identifiers: names, addresses, dates, phone/fax, email, SSN, MRN, health plan IDs, account numbers, license numbers, vehicle/device IDs, URLs, IP addresses, biometric IDs, photo references, and other identifiers (facility names, etc.).

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region | `us-east-1` |
| `BEDROCK_MODEL_ID` | Bedrock model | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| `LOGFIRE_API_KEY` | Logfire key (optional) | - |
| `LOGFIRE_PROJECT` | Logfire project (optional) | - |