#!/usr/bin/env python3
"""
CLI script for evaluating de-identification solution output against ground truth.

Usage:
    python evaluate.py --ground-truth output/manifests --solution solution_output/
    python evaluate.py -g output/manifests -s solution_output/ -o evaluation_report.json
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluator import Evaluator


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate de-identification solution against ground truth"
    )
    parser.add_argument(
        "-g", "--ground-truth",
        type=str,
        required=True,
        help="Path to ground truth manifests directory"
    )
    parser.add_argument(
        "-s", "--solution",
        type=str,
        required=True,
        help="Path to solution output directory (JSON files with phi_entities)"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Path to save evaluation report JSON (optional)"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="value",
        choices=["value", "position", "strict"],
        help="Matching mode: value (type+value), position (type+overlap), strict (all)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    ground_truth_dir = Path(args.ground_truth)
    solution_dir = Path(args.solution)

    if not ground_truth_dir.exists():
        print(f"Error: Ground truth directory not found: {ground_truth_dir}")
        sys.exit(1)

    if not solution_dir.exists():
        print(f"Error: Solution output directory not found: {solution_dir}")
        sys.exit(1)

    print(f"Ground truth: {ground_truth_dir}")
    print(f"Solution output: {solution_dir}")
    print(f"Matching mode: {args.mode}")
    print("-" * 60)

    evaluator = Evaluator(match_mode=args.mode)

    # Run evaluation
    evaluations, aggregate = evaluator.evaluate_batch(ground_truth_dir, solution_dir)

    if not evaluations:
        print("No notes were evaluated. Check that file names match between directories.")
        sys.exit(1)

    # Print report
    evaluator.print_evaluation_report(evaluations, aggregate)

    # Save report if requested
    if args.output:
        output_path = Path(args.output)
        evaluator.save_evaluation_report(evaluations, aggregate, output_path)


if __name__ == "__main__":
    main()
