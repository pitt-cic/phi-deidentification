#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Build the frontend and deploy it to the Amplify app created by CDK.

Usage:
  ./deploy-frontend.sh [options]

Options:
  --stack-name <name>    CloudFormation stack name (default: PiiDeidentificationStack)
  --app-id <id>          Amplify app ID override (otherwise parsed from AmplifyAppUrl output)
  --branch <name>        Amplify branch override (otherwise parsed from AmplifyAppUrl output)
  --profile <profile>    AWS profile to use
  --region <region>      AWS region override
  --skip-install         Skip bun ci before build
  -h, --help             Show this help text
EOF
}

STACK_NAME="PiiDeidentificationStackV4"
APP_ID=""
BRANCH_NAME=""
PROFILE=""
REGION=""
SKIP_INSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack-name)
      STACK_NAME="${2:-}"
      shift 2
      ;;
    --app-id)
      APP_ID="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH_NAME="${2:-}"
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
    --skip-install)
      SKIP_INSTALL=1
      shift
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

for cmd in aws bun curl zip mktemp; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command '$cmd' is not available in PATH." >&2
    exit 1
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

get_stack_output() {
  local key="$1"
  local value

  if ! value="$(run_aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$key'].OutputValue | [0]" \
    --output text 2>/dev/null)"; then
    echo "Error: unable to read CloudFormation stack '$STACK_NAME'." >&2
    exit 1
  fi

  if [[ -z "$value" || "$value" == "None" ]]; then
    echo "Error: output '$key' not found in stack '$STACK_NAME'." >&2
    exit 1
  fi

  printf '%s\n' "$value"
}

echo "Loading backend outputs from stack '$STACK_NAME'..." >&2
API_URL="$(get_stack_output "ApiUrl")"
USER_POOL_ID="$(get_stack_output "UserPoolId")"
USER_POOL_CLIENT_ID="$(get_stack_output "UserPoolClientId")"
AMPLIFY_APP_URL="$(get_stack_output "AmplifyAppUrl")"

if [[ -z "$APP_ID" || -z "$BRANCH_NAME" ]]; then
  host="${AMPLIFY_APP_URL#https://}"
  host="${host#http://}"
  host="${host%%/*}"

  if [[ "$host" =~ ^([^.]+)\.([^.]+)\.amplifyapp\.com$ ]]; then
    parsed_branch="${BASH_REMATCH[1]}"
    parsed_app_id="${BASH_REMATCH[2]}"
  else
    echo "Error: could not parse app ID/branch from AmplifyAppUrl '$AMPLIFY_APP_URL'." >&2
    echo "Pass --app-id and --branch explicitly." >&2
    exit 1
  fi

  if [[ -z "$APP_ID" ]]; then
    APP_ID="$parsed_app_id"
  fi
  if [[ -z "$BRANCH_NAME" ]]; then
    BRANCH_NAME="$parsed_branch"
  fi
fi

echo "Amplify target: appId=$APP_ID branch=$BRANCH_NAME" >&2

cd "$SCRIPT_DIR"

if [[ "$SKIP_INSTALL" -eq 0 ]]; then
  echo "Installing frontend dependencies..." >&2
  bun install
fi

# Clean previous build artifacts
rm -rf dist

echo "Building frontend..." >&2
VITE_API_URL="$API_URL" \
VITE_USER_POOL_ID="$USER_POOL_ID" \
VITE_USER_POOL_CLIENT_ID="$USER_POOL_CLIENT_ID" \
bun run build

if [[ ! -d dist ]]; then
  echo "Error: build did not produce frontend/dist." >&2
  exit 1
fi

ZIP_FILE="amplify-deploy-$(date +%Y%m%d-%H%M%S).zip"
# trap 'rm -f "$ZIP_FILE"' EXIT

echo "Packaging dist bundle..." >&2
(cd dist && zip -r "$ZIP_FILE" .)

echo "Creating Amplify deployment..." >&2
read -r ZIP_UPLOAD_URL JOB_ID <<< "$(run_aws amplify create-deployment \
  --app-id "$APP_ID" \
  --branch-name "$BRANCH_NAME" \
  --query '[zipUploadUrl,jobId]' \
  --output text)"

if [[ -z "$ZIP_UPLOAD_URL" || -z "$JOB_ID" || "$ZIP_UPLOAD_URL" == "None" || "$JOB_ID" == "None" ]]; then
  echo "Error: failed to create Amplify deployment job." >&2
  exit 1
fi

echo "Uploading artifact to Amplify..." >&2
curl -sSfL -X PUT \
  -H "Content-Type: application/zip" \
  --upload-file "dist/$ZIP_FILE" \
  "$ZIP_UPLOAD_URL" >/dev/null

echo "Starting Amplify deployment job $JOB_ID..." >&2
run_aws amplify start-deployment \
  --app-id "$APP_ID" \
  --branch-name "$BRANCH_NAME" \
  --job-id "$JOB_ID" >/dev/null

if [ $? -ne 0 ]; then
    echo "❌ Failed to start deployment"
    rm -f "dist/$ZIP_FILE"
    exit 1
fi

echo "Deployment started." >&2
echo "App URL: $AMPLIFY_APP_URL" >&2
echo "Job ID: $JOB_ID" >&2
echo >&2
echo "Check deployment status with:" >&2
echo "aws amplify get-job --app-id \"$APP_ID\" --branch-name \"$BRANCH_NAME\" --job-id \"$JOB_ID\" --query 'job.summary.status' --output text" >&2
