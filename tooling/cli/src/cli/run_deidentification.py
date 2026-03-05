"""Main module for processing documents with the Bedrock-backed PHI agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from deidentification.redaction import (
    FormatterProtocol,
    RedactionFormat,
    RedactionFormatManager,
    RedactionFormatter
)
from deidentification import (
    load_document,
    build_detection_params,
    build_response_payload,
    process_document,
    process_dataset
)
from deidentification.constants import DEFAULT_MAX_CHARS

logger = logging.getLogger("pii_deidentification.main")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Bedrock-backed PHI agent against a text document.",
    )
    parser.add_argument(
        "input_path",
        type=Path,
        nargs="?",
        help="Path to the UTF-8 text file to analyze. Use '-' to read from stdin.",
    )
    parser.add_argument(
        "--source-name",
        help="Optional identifier for logs and output (defaults to file path).",
    )
    parser.add_argument(
        "--pii-types",
        nargs="+",
        default=None,
        metavar="TYPE",
        help="Override the default PHI categories (space-separated list).",
    )
    parser.add_argument(
        "--max-entities",
        type=int,
        default=None,
        help="Maximum number of PHI spans the agent should return.",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Language of the document (IETF BCP-47 tag).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help="Maximum allowed document length in characters (default: 20k).",
    )
    parser.add_argument(
        "--raw-response",
        action="store_true",
        help="Print only the AgentResponse payload instead of metadata-wrapped JSON.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("synthetic_dataset/notes"),
        help="Directory containing .txt files to process instead of a single document.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory where JSON results will be written (dataset mode).",
    )
    parser.add_argument(
        "--no-redact",
        action="store_true",
        help="Skip automatic PHI redaction after processing (dataset mode only).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Maximum number of documents to process concurrently (default: 3).",
    )
    
    # Custom redaction format options
    format_group = parser.add_argument_group("Custom Redaction Format")
    format_group.add_argument(
        "--custom",
        metavar="FORMAT_NAME",
        help="Use a saved custom redaction format by name.",
    )
    format_group.add_argument(
        "--define-format",
        metavar="TEMPLATE",
        help="Define a custom format template. Use {TYPE} for PHI type and {ID} for "
             "unique identifier. Examples: '[REDACTED]', '[{TYPE}]', '**{TYPE}[{ID}]'",
    )
    format_group.add_argument(
        "--id-scheme",
        choices=["alpha", "numeric"],
        default="alpha",
        help="Identifier scheme: 'alpha' (A,B,C...) or 'numeric' (1,2,3...). Default: alpha",
    )
    format_group.add_argument(
        "--save-as",
        metavar="NAME",
        help="Save the defined format with this name for future use.",
    )
    format_group.add_argument(
        "--list-formats",
        action="store_true",
        help="List all saved custom formats and exit.",
    )
    
    return parser.parse_args()


def create_formatter_from_args(args: argparse.Namespace) -> FormatterProtocol | None:
    """Create a formatter based on command line arguments.
    
    Args:
        args: Parsed command line arguments.
        
    Returns:
        A RedactionFormatter if custom format is specified, None for default format.
        
    Raises:
        FileNotFoundError: If --custom specifies a non-existent format.
        ValueError: If --define-format template is invalid.
    """
    manager = RedactionFormatManager()
    
    # Load existing format by name
    if args.custom:
        fmt = manager.load(args.custom)
        logger.info("Using custom format '%s': %s", args.custom, fmt.template)
        return RedactionFormatter(fmt)
    
    # Create new format from template
    if args.define_format:
        fmt = RedactionFormat(
            template=args.define_format,
            id_scheme=args.id_scheme,
            name=args.save_as,
        )
        
        # Save if requested
        if args.save_as:
            manager.save(fmt)
            logger.info("Saved format '%s'", args.save_as)
        
        logger.info("Using custom format: %s (id_scheme=%s)", fmt.template, fmt.id_scheme)
        return RedactionFormatter(fmt)
    
    # No custom format specified, use default
    return None


def list_available_formats() -> None:
    """Print all available custom redaction formats."""
    manager = RedactionFormatManager()
    formats = manager.list_formats()
    
    if formats:
        print("Available custom redaction formats:")
        print()
        for name in formats:
            try:
                fmt = manager.load(name)
                print(f"  {name}")
                print(f"    Template:  {fmt.template}")
                print(f"    ID Scheme: {fmt.id_scheme}")
                if fmt.created:
                    print(f"    Created:   {fmt.created}")
                print()
            except Exception as e:
                print(f"  {name}: (error loading: {e})")
                print()
        print("Use --custom <name> to use a saved format.")
    else:
        print("No saved formats found.")
        print()
        print("Create a format with:")
        print("  --define-format '<template>' --id-scheme <alpha|numeric> --save-as <name>")
        print()
        print("Example:")
        print("  python main.py --define-format '**{TYPE}[{ID}]' --id-scheme alpha --save-as hipaa")

async def run_cli() -> None:
    args = parse_args()
    
    # Handle --list-formats first (exit early)
    if args.list_formats:
        list_available_formats()
        return
    
    # Create formatter from custom format arguments
    formatter = create_formatter_from_args(args)
    
    detection = build_detection_params(
        pii_types=args.pii_types,
        max_entities=args.max_entities,
    )

    if args.dataset is not None:
        await process_dataset(
            args.dataset,
            detection=detection,
            language=args.language,
            max_chars=args.max_chars,
            raw_response=args.raw_response,
            output_dir=args.output_dir,
            auto_redact=not args.no_redact,
            concurrency=args.concurrency,
            formatter=formatter,
        )
        return

    if args.input_path is None:
        logger.error("You must supply either an input_path or --dataset.")
        raise SystemExit(2)

    document_text = load_document(args.input_path)
    source_name = args.source_name or str(args.input_path)
    response = await process_document(
        document_text,
        source_name=source_name,
        detection=detection,
        language=args.language,
        max_chars=args.max_chars,
    )
    payload = build_response_payload(response, source_name, args.language, detection, args.raw_response)
    print(json.dumps(payload, indent=2))

def main() -> None:
    try:
        asyncio.run(run_cli())
    except (FileNotFoundError, ValueError, OSError) as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc

if __name__ == "__main__":
    main()
