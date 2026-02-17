#!/usr/bin/env python3
"""
CLI script for generating clinical notes with PHI using LLM.

Usage:
    python generate_notes.py --type emergency_dept --count 5
    python generate_notes.py --type all --count 2
    python generate_notes.py --type discharge_summary,progress_note --count 3
"""

import argparse
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
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible PHI generation"
    )
    return parser.parse_args()


def get_note_types(type_arg: str) -> list:
    """Parse the type argument into a list of NoteTypes."""
    if type_arg.lower() == "all":
        return list(NoteType)

    type_map = {
        "emergency_dept": NoteType.EMERGENCY_DEPT,
        "ed": NoteType.EMERGENCY_DEPT,
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


def main():
    args = parse_args()

    note_types = get_note_types(args.type)
    if not note_types:
        print("Error: No valid note types specified")
        sys.exit(1)

    output_dir = Path(args.output)
    config = GeneratorConfig(output_dir=output_dir)
    config.ensure_dirs()

    print(f"Output directory: {output_dir.absolute()}")
    print(f"Note types: {[nt.value for nt in note_types]}")
    print(f"Count per type: {args.count}")
    print("-" * 60)

    generator = NoteGenerator(config=config)

    total_generated = 0
    for note_type in note_types:
        print(f"\nGenerating {args.count} {note_type.value} note(s)...")
        try:
            notes = generator.generate_and_save(note_type, count=args.count, output_dir=output_dir)
            total_generated += len(notes)
        except Exception as e:
            print(f"Error generating {note_type.value}: {e}")
            continue

    print("\n" + "=" * 60)
    print(f"Total notes generated: {total_generated}")
    print(f"Notes saved to: {output_dir / 'notes'}")
    print(f"Manifests saved to: {output_dir / 'manifests'}")


if __name__ == "__main__":
    main()
