#!/usr/bin/env python3
"""
CLI script for generating clinical notes with PHI using LLM.

Usage:
    # Generate from Faker (no FHIR bundle)
    python generate_notes.py --type emergency_dept --count 2

    # Generate from FHIR bundle
    python generate_notes.py --type all --bundle ../synthea-example/*.json

    # Generate templates for bulk generation
    python generate_notes.py --type all --bundle ../synthea-example/*.json --template

    # Generate all 5 note types
    python generate_notes.py --type all --count 1
"""

import argparse
import glob
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import NoteType, GeneratorConfig
from src.note_generator import NoteGenerator


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate clinical notes with embedded PHI using LLM"
    )
    parser.add_argument(
        "-t", "--type",
        type=str,
        required=True,
        help="Note type(s) to generate. Options: emergency_dept, discharge_summary, "
             "progress_note, radiology_report, telehealth_consult, all, or comma-separated list"
    )
    parser.add_argument(
        "-c", "--count",
        type=int,
        default=1,
        help="Number of notes to generate per type (default: 1)"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="output",
        help="Output directory (default: output)"
    )
    parser.add_argument(
        "-b", "--bundle",
        type=str,
        default=None,
        help="Path to FHIR bundle JSON file (supports glob patterns like *.json). "
             "If not provided, generates PHI using Faker."
    )
    parser.add_argument(
        "--template",
        action="store_true",
        help="Generate templates with {{PLACEHOLDERS}} instead of filled notes"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible PHI generation (Faker mode only)"
    )
    return parser.parse_args()


def get_note_types(type_arg: str) -> list:
    """Parse the type argument into a list of NoteTypes."""
    if type_arg.lower() == "all":
        return list(NoteType)

    type_map = {
        "emergency_dept": NoteType.EMERGENCY_DEPT,
        "ed": NoteType.EMERGENCY_DEPT,
        "emergency": NoteType.EMERGENCY_DEPT,
        "discharge_summary": NoteType.DISCHARGE_SUMMARY,
        "discharge": NoteType.DISCHARGE_SUMMARY,
        "progress_note": NoteType.PROGRESS_NOTE,
        "progress": NoteType.PROGRESS_NOTE,
        "soap": NoteType.PROGRESS_NOTE,
        "radiology_report": NoteType.RADIOLOGY_REPORT,
        "radiology": NoteType.RADIOLOGY_REPORT,
        "rad": NoteType.RADIOLOGY_REPORT,
        "telehealth_consult": NoteType.TELEHEALTH_CONSULT,
        "telehealth": NoteType.TELEHEALTH_CONSULT,
        "tele": NoteType.TELEHEALTH_CONSULT,
    }

    types = []
    for t in type_arg.lower().split(","):
        t = t.strip()
        if t in type_map:
            types.append(type_map[t])
        else:
            print(f"Warning: Unknown note type '{t}', skipping")

    return types


def get_bundle_paths(bundle_arg: str) -> list:
    """Expand glob patterns and return list of bundle paths."""
    if not bundle_arg:
        return []

    # Expand glob pattern
    paths = glob.glob(bundle_arg)
    if not paths:
        # Try as direct path
        path = Path(bundle_arg)
        if path.exists():
            return [path]
        else:
            print(f"Warning: No files found matching '{bundle_arg}'")
            return []

    return [Path(p) for p in paths if Path(p).suffix == '.json']


def main():
    args = parse_args()

    note_types = get_note_types(args.type)
    if not note_types:
        print("Error: No valid note types specified")
        sys.exit(1)

    output_dir = Path(args.output)
    config = GeneratorConfig(output_dir=output_dir)
    config.ensure_dirs()

    # Get bundle paths if provided
    bundle_paths = get_bundle_paths(args.bundle) if args.bundle else []

    print(f"Output directory: {output_dir.absolute()}")
    print(f"Note types: {[nt.value for nt in note_types]}")
    print(f"Template mode: {args.template}")
    if bundle_paths:
        print(f"FHIR bundles: {len(bundle_paths)} file(s)")
    else:
        print("Data source: Faker (synthetic PHI)")
    print(f"Count per type: {args.count}")
    print("-" * 60)

    generator = NoteGenerator(config=config)

    total_generated = 0

    if bundle_paths:
        # Generate from FHIR bundles
        for bundle_path in bundle_paths:
            print(f"\nProcessing bundle: {bundle_path.name}")
            for note_type in note_types:
                print(f"\nGenerating {args.count} {note_type.value} {'templates' if args.template else 'notes'}...")
                try:
                    for i in range(args.count):
                        note = generator.generate_from_fhir(
                            bundle_path=bundle_path,
                            note_type=note_type,
                            template_mode=args.template
                        )
                        generator.save_note(note, output_dir)
                        total_generated += 1
                except Exception as e:
                    print(f"Error generating {note_type.value}: {e}")
                    continue
    else:
        # Generate from Faker
        for note_type in note_types:
            print(f"\nGenerating {args.count} {note_type.value} {'templates' if args.template else 'notes'}...")
            try:
                for i in range(args.count):
                    note = generator.generate_from_faker(
                        note_type=note_type,
                        template_mode=args.template
                    )
                    generator.save_note(note, output_dir)
                    total_generated += 1
            except Exception as e:
                print(f"Error generating {note_type.value}: {e}")
                continue

    print("\n" + "=" * 60)
    print(f"Total {'templates' if args.template else 'notes'} generated: {total_generated}")
    print(f"Notes saved to: {output_dir / 'notes'}")
    print(f"Manifests saved to: {output_dir / 'manifests'}")

    if args.template:
        print("\nNext step: Use generate_bulk.py with --template-dir to generate filled notes")


if __name__ == "__main__":
    main()
