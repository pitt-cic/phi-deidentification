#!/usr/bin/env bash
set -euo pipefail

# Run tests for each workspace member
# This is needed because lambda packages are not installed as Python packages

echo "Running Lambda API tests..."
cd lambda/api && uv run pytest tests/ -v

echo -e "\nRunning Lambda Ingestion tests..."
cd ../ingestion && uv run pytest tests/ -v

echo -e "\nRunning Lambda Worker tests..."
cd ../worker && uv run pytest tests/ -v

echo -e "\nAll tests passed!"
