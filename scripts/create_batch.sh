#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Create batch metadata in S3 and print the batch ID.

Usage:
  ./scripts/create_batch.sh --bucket <bucket-name> [options]

Required:
  --bucket <name>         S3 bucket name

Optional:
  --batch-id <id>         Use a specific batch id
  --profile <profile>     AWS profile to use
  --region <region>       AWS region override
  -h, --help              Show this help message
EOF
}

BUCKET=""
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

if [[ -z "$BUCKET" ]]; then
  echo "Error: --bucket is required." >&2
  usage
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "Error: aws CLI is not installed or not in PATH." >&2
  exit 1
fi

if [[ -z "$BATCH_ID" ]]; then
  BATCH_ID="batch-$(date -u +%Y%m%d%H%M%S)-$RANDOM"
fi

CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
METADATA_PAYLOAD="$(printf '{"batch_id":"%s","created_at":"%s","status":"created","all_approved":false}\n' "$BATCH_ID" "$CREATED_AT")"

AWS_ARGS=()
if [[ -n "$PROFILE" ]]; then
  AWS_ARGS+=(--profile "$PROFILE")
fi
if [[ -n "$REGION" ]]; then
  AWS_ARGS+=(--region "$REGION")
fi

printf '%s' "$METADATA_PAYLOAD" \
  | aws "${AWS_ARGS[@]}" s3 cp - "s3://$BUCKET/$BATCH_ID/metadata.json" --content-type application/json >/dev/null

echo "Created metadata: s3://$BUCKET/$BATCH_ID/metadata.json" >&2
echo "Batch ID: $BATCH_ID" >&2
printf '%s\n' "$BATCH_ID"
