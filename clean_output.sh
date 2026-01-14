#!/bin/bash

# Script to clear output folders

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Cleaning output folders..."

# Remove output directories if they exist
for dir in output output-text output-json; do
    if [ -d "$dir" ]; then
        rm -rf "$dir"
        echo "  Removed $dir/"
    fi
done

echo "Done!"
