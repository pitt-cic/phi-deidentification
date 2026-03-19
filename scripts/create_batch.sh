#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Create a batch input folder in your existing S3 bucket, optionally upload notes, and print the batch ID.

Usage:
  ./scripts/create_batch.sh [options]

Optional:
  --bucket <name>         S3 bucket name (if omitted, resolved from stack output)
  --stack-name <name>     CloudFormation stack name for bucket lookup (default: PHIDeidentificationStack)
  --notes-dir <path>      Upload .txt files from this directory to input/
  --batch-id <id>         Use a specific batch id
  --profile <profile>     AWS profile to use
  --region <region>       AWS region override
  -h, --help              Show this help message
EOF
}

BUCKET=""
STACK_NAME="PHIDeidentificationStack"
NOTES_DIR=""
BATCH_ID=""
PROFILE=""
REGION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bucket)
      BUCKET="${2:-}"
      shift 2
      ;;
    --batch-id)
      BATCH_ID="${2:-}"
      shift 2
      ;;
    --stack-name)
      STACK_NAME="${2:-}"
      shift 2
      ;;
    --notes-dir)
      NOTES_DIR="${2:-}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:-}"
      shift 2
      ;;
    --region)
      REGION="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v aws >/dev/null 2>&1; then
  echo "Error: aws CLI is not installed or not in PATH." >&2
  exit 1
fi

run_aws() {
  if [[ -n "$PROFILE" && -n "$REGION" ]]; then
    aws --profile "$PROFILE" --region "$REGION" "$@"
    return
  fi

  if [[ -n "$PROFILE" ]]; then
    aws --profile "$PROFILE" "$@"
    return
  fi

  if [[ -n "$REGION" ]]; then
    aws --region "$REGION" "$@"
    return
  fi

  aws "$@"
}

if [[ -z "$BUCKET" ]]; then
  BUCKET="$(run_aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue | [0]" \
    --output text 2>/dev/null || true)"
  if [[ -z "$BUCKET" || "$BUCKET" == "None" ]]; then
    echo "Error: Could not resolve bucket from stack '$STACK_NAME'. Provide --bucket explicitly or verify AWS credentials/region." >&2
    exit 1
  fi
  echo "Resolved bucket from stack '$STACK_NAME': $BUCKET" >&2
fi

batch_exists() {
  local candidate="$1"
  local key_count
  key_count="$(run_aws s3api list-objects-v2 \
    --bucket "$BUCKET" \
    --prefix "$candidate/" \
    --max-keys 1 \
    --query 'length(Contents)' \
    --output text 2>/dev/null || echo "0")"

  [[ "$key_count" != "0" && "$key_count" != "None" ]]
}

# Capture timestamp once for consistency between batch ID and created_at
TIMESTAMP_COMPACT="$(date -u +%Y%m%d%H%M%S)"
TIMESTAMP_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ -z "$BATCH_ID" ]]; then
  BASE_BATCH_ID="batch-${TIMESTAMP_COMPACT}"
  BATCH_ID="$BASE_BATCH_ID"
  SUFFIX=1
  while batch_exists "$BATCH_ID"; do
    BATCH_ID="${BASE_BATCH_ID}-${SUFFIX}"
    SUFFIX=$((SUFFIX + 1))
  done
fi

run_aws s3api put-object \
  --bucket "$BUCKET" \
  --key "$BATCH_ID/input/" >/dev/null

echo "Created input folder: s3://$BUCKET/$BATCH_ID/input/" >&2

if [[ -n "$NOTES_DIR" ]]; then
  if [[ ! -d "$NOTES_DIR" ]]; then
    echo "Error: --notes-dir must be an existing directory." >&2
    exit 1
  fi

  run_aws s3 cp "$NOTES_DIR" "s3://$BUCKET/$BATCH_ID/input/" \
    --recursive --exclude "*" --include "*.txt" >/dev/null
  echo "Uploaded .txt files from $NOTES_DIR to s3://$BUCKET/$BATCH_ID/input/" >&2
fi

echo "Batch ID: $BATCH_ID" >&2

# Create DynamoDB entry for the batch
STATS_TABLE="$(run_aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='BatchStatsTableName'].OutputValue | [0]" \
  --output text 2>/dev/null || true)"

if [[ -z "$STATS_TABLE" || "$STATS_TABLE" == "None" ]]; then
  echo "Warning: Could not resolve stats table from stack '$STACK_NAME'. DynamoDB entry not created." >&2
else
  if [[ -n "$NOTES_DIR" ]]; then
    STATUS="ready"
    INPUT_COUNT=$(find "$NOTES_DIR" -maxdepth 1 -name "*.txt" -type f 2>/dev/null | wc -l | tr -d ' ')
  else
    STATUS="created"
    INPUT_COUNT=0
  fi

  run_aws dynamodb put-item \
    --table-name "$STATS_TABLE" \
    --item "{
      \"batch_id\": {\"S\": \"$BATCH_ID\"},
      \"record_type\": {\"S\": \"BATCH\"},
      \"status\": {\"S\": \"$STATUS\"},
      \"input_count\": {\"N\": \"$INPUT_COUNT\"},
      \"processed_count\": {\"N\": \"0\"},
      \"approved_count\": {\"N\": \"0\"},
      \"total_entities\": {\"N\": \"0\"},
      \"notes_with_pii\": {\"N\": \"0\"},
      \"created_at\": {\"S\": \"$TIMESTAMP_ISO\"}
    }" 2>/dev/null || echo "Warning: Failed to create DynamoDB entry" >&2

  echo "Created DynamoDB entry: status=$STATUS, input_count=$INPUT_COUNT" >&2
fi

printf '%s\n' "$BATCH_ID"
