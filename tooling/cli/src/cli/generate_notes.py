#!/usr/bin/env python3
"""
CLI script for generating clinical notes with PHI using LLM.

Usage:
    # Generate from Faker (no FHIR bundle)
    python generate_notes.py --type emergency_dept --count 2

    # Generate from local FHIR bundle
    python generate_notes.py --type all --bundle ../synthea-example/*.json

    # Generate from S3 FHIR bundles
    python generate_notes.py --type all --bundle s3://synthea-open-data/coherent/unzipped/fhir/*.json --max-bundles 10

    # Generate templates for bulk generation
    python generate_notes.py --type all --bundle s3://bucket/path/*.json --template

    # Save output to S3
    python generate_notes.py --type all --bundle s3://input-bucket/path/*.json --s3-output s3://output-bucket/notes/
"""

import argparse
import asyncio
import sys
import tempfile
import traceback

from pathlib import Path

# Add parent directory to path for imports
# sys.path.insert(0, str(Path(__file__).parent.parent))

from synthetic_data_generator.config import GeneratorConfig
from synthetic_data_generator.note_generator import NoteGenerator
from synthetic_data_generator.local_file_client import LocalFileClient
from synthetic_data_generator.s3_client import S3Client
from synthetic_data_generator.models.utils import get_note_types
import synthetic_data_generator.utils as utils

class CLIArgs(argparse.Namespace):
    type: str
    count: int = 1
    output: str = "output"
    bundle: str | None = None
    max_bundles: int | None = None
    template: bool = False
    s3_output: str | None = None
    seed: int | None = None
    use_async: bool = False
    rate_limit: int = 150

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
        default="data/input",
        help="Output directory (default: output)"
    )
    parser.add_argument(
        "-b", "--bundle",
        type=str,
        default=None,
        help="Path to FHIR bundle JSON file(s). Supports: "
             "local paths with glob patterns (*.json), "
             "S3 paths (s3://bucket/path/*.json). "
             "If not provided, generates PHI using Faker."
    )
    parser.add_argument(
        "--template",
        action="store_true",
        help="Generate templates with {{PLACEHOLDERS}} instead of filled notes"
    )
    parser.add_argument(
        "--max-bundles",
        type=int,
        default=None,
        help="Maximum number of FHIR bundles to process (useful for testing)"
    )
    parser.add_argument(
        "--s3-output",
        type=str,
        default=None,
        help="S3 path to save output (e.g., s3://bucket/path/). "
             "If not provided, saves locally to --output directory."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible PHI generation (Faker mode only)"
    )
    parser.add_argument(
        "--async",
        action="store_true",
        dest="use_async",
        help="Use async generation with rate limiting (recommended for large batches)"
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=150,
        help="Max requests per minute for async mode (default: 150)"
    )
    return parser.parse_args(namespace=CLIArgs())

def main():
    args = parse_args()

    note_types = get_note_types(args.type)
    if not note_types:
        print("Error: No valid note types specified")
        sys.exit(1)

    output_dir = Path(args.output)
    config = GeneratorConfig(output_dir=output_dir, s3_output_path=args.s3_output)
    config.ensure_dirs(template_mode=args.template)

    s3_client = S3Client()
    local_file_client = LocalFileClient()

    bundles = []
    is_s3 = utils.is_s3_path(args.bundle)
    if args.bundle is None:
        bundles = [] # Faker mode - no bundles to process
    elif is_s3:
        bucket, prefix = utils.parse_s3_path(args.bundle)
        bundles = s3_client.list_objects(
            bucket,
            prefix,
            pattern="*.json",
            exclude_objects=['organizations.json', 'practitioners.json'],
            limit=args.max_bundles,
        )
    else:
        bundles = local_file_client.list_local_files(
            args.bundle,
            pattern="*.json",
            exclude_files=['organizations.json', 'practitioners.json'],
            limit=args.max_bundles,
        )

    print(f"Output directory: {output_dir.absolute()}")
    if args.s3_output:
        print(f"S3 output: {args.s3_output}")
    print(f"Note types: {[nt.value for nt in note_types]}")
    print(f"Template mode: {args.template}")
    if bundles:
        source = "S3" if is_s3 else "Local"
        print(f"FHIR bundles: {len(bundles)} file(s) ({source})")
        if args.max_bundles:
            print(f"Max bundles limit: {args.max_bundles}")
    else:
        print("Data source: Faker (synthetic PHI)")
    print(f"Count per type: {args.count}")
    print("-" * 60)

    # Dispatch to async or sync mode
    if args.use_async:
        if is_s3:
            print("Error: Async mode does not yet support S3 bundles. Use local bundles.")
            sys.exit(1)
        asyncio.run(async_main(args, bundles, note_types, config))
        return  # Exit after async completion

    generator = NoteGenerator(config=config)

    total_generated = 0
    total_skipped = 0

    if bundles:
        # Generate from FHIR bundles
        if is_s3:
            # S3 mode: download → process → delete → next
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                for bundle_info in bundles:
                    bundle_filename = bundle_info['filename']
                    print(f"\nProcessing S3 bundle: {bundle_filename}")

                    try:
                        # Download from S3
                        print(f"  Downloading from s3://{bundle_info['bucket']}/{bundle_info['key']}...")
                        local_bundle_path = s3_client.download_file(
                            bundle_info['bucket'],
                            bundle_info['key'],
                            temp_path
                        )

                        # Process bundle
                        for note_type in note_types:
                            try:
                                for i in range(args.count):
                                    # Generate note ID based on template mode
                                    if args.template:
                                        # Use bundle filename (without .json) for templates
                                        bundle_base = bundle_filename.replace('.json', '')
                                        note_id = f"{note_type.value}_{bundle_base}_template"
                                    else:
                                        note_id = None  # Use auto-generated sequential ID

                                    note = generator.generate_from_fhir(
                                        bundle_path=local_bundle_path,
                                        note_type=note_type,
                                        note_id=note_id,
                                        template_mode=args.template
                                    )
                                    generator.save_note(note)

                                    # Upload to S3 if requested
                                    # if args.s3_output:
                                    #     if note.is_template:
                                    #         note_path = config.template_notes_dir / f"{note.note_id}.txt"
                                    #         manifest_path = config.template_manifests_dir / f"{note.note_id}.json"
                                    #     else:
                                    #         note_path = config.notes_dir / f"{note.note_id}.txt"
                                    #         manifest_path = config.manifests_dir / f"{note.note_id}.json"
                                    #     upload_to_s3(note_path, args.s3_output)
                                    #     upload_to_s3(manifest_path, args.s3_output)

                                    total_generated += 1
                            except Exception as e:
                                traceback.print_exc()
                                print(f"  Error generating {note_type.value}: {e}")
                                total_skipped += 1
                                continue

                        # Clean up: delete local file
                        local_bundle_path.unlink()

                    except Exception as e:
                        print(f"  Error processing bundle {bundle_filename}: {e}")
                        print("  Skipping bundle and continuing...")
                        total_skipped += 1
                        continue
        else:
            # Local mode
            for bundle_path in bundles:
                print(f"\nProcessing local bundle: {bundle_path.name}")

                try:
                    for note_type in note_types:
                        try:
                            for i in range(args.count):
                                # Generate note ID based on template mode
                                if args.template:
                                    # Use bundle filename (without .json) for templates
                                    bundle_base = bundle_path.stem
                                    note_id = f"{note_type.value}_{bundle_base}_template"
                                else:
                                    note_id = None  # Use auto-generated sequential ID

                                note = generator.generate_from_fhir(
                                    bundle_path=bundle_path,
                                    note_type=note_type,
                                    note_id=note_id,
                                    template_mode=args.template
                                )
                                generator.save_note(note)

                                # Upload to S3 if requested
                                # if args.s3_output:
                                #     note_path = output_dir / config.notes_subdir / f"{note.note_id}.txt"
                                #     manifest_path = output_dir / config.manifests_subdir / f"{note.note_id}.json"
                                #     upload_to_s3(note_path, args.s3_output)
                                #     upload_to_s3(manifest_path, args.s3_output)

                                total_generated += 1
                        except Exception as e:
                            print(f"  Error generating {note_type.value}: {e}")
                            total_skipped += 1
                            continue
                except Exception as e:
                    print(f"  Error processing bundle {bundle_path.name}: {e}")
                    print("  Skipping bundle and continuing...")
                    total_skipped += 1
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
                    generator.save_note(note)

                    # Upload to S3 if requested
                    # if args.s3_output:
                    #     note_path = output_dir / config.notes_subdir / f"{note.note_id}.txt"
                    #     manifest_path = output_dir / config.manifests_subdir / f"{note.note_id}.json"
                    #     upload_to_s3(note_path, args.s3_output)
                    #     upload_to_s3(manifest_path, args.s3_output)

                    total_generated += 1
            except Exception as e:
                print(f"Error generating {note_type.value}: {e}")
                total_skipped += 1
                continue

    print("\n" + "=" * 60)
    print(f"Total {'templates' if args.template else 'notes'} generated: {total_generated}")
    if total_skipped > 0:
        print(f"Total skipped (errors): {total_skipped}")

    if args.s3_output:
        print(f"Output saved to: {config.s3_output_path}")
    elif args.template:
        print(f"Template notes saved to: {config.template_notes_dir}")
        print(f"Template manifests saved to: {config.template_manifests_dir}")
        print("\nNext step: Use generate_bulk.py with --template-dir to generate filled notes")
    else:
        print(f"Notes saved to: {config.notes_dir}")
        print(f"Manifests saved to: {config.manifests_dir}")


async def async_main(args: CLIArgs, bundles: list, note_types: list, config):
    """Async entry point for concurrent note generation."""
    from synthetic_data_generator.async_note_generator import AsyncNoteGenerator

    generator = AsyncNoteGenerator(config=config, rate_limit=args.rate_limit)

    # Build task list
    tasks = []
    for bundle_info in bundles:
        # Handle S3 vs local bundles
        if isinstance(bundle_info, dict):
            # S3 bundle - not supported in async mode yet
            print("Warning: S3 bundles not yet supported in async mode. Use local bundles.")
            return
        else:
            bundle_path = bundle_info

        for note_type in note_types:
            for _ in range(args.count):
                tasks.append((bundle_path, note_type))

    print(f"\nAsync mode enabled")
    print(f"Rate limit: {args.rate_limit} RPM")
    print(f"Total tasks: {len(tasks)}")
    print(f"Estimated time: ~{len(tasks) / args.rate_limit:.1f} minutes")
    print("-" * 60)

    notes, errors = await generator.generate_all(
        tasks=tasks,
        template_mode=args.template
    )

    print("\n" + "=" * 60)
    print(f"Total notes generated: {len(notes)}")
    if errors:
        print(f"Total errors: {len(errors)}")
        for i, err in enumerate(errors[:10]):  # Show first 10 errors
            print(f"  {i+1}. {type(err).__name__}: {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")


if __name__ == "__main__":
    main()
