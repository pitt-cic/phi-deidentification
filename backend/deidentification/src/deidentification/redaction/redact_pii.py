"""Script to redact PII from text files based on JSON annotation files."""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Protocol

from .redaction_formats import (
    DefaultFormatter,
    RedactionFormat,
    RedactionFormatManager,
    RedactionFormatter,
)

logger = logging.getLogger("pii_deidentification.redact")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

# PII type processing order - containers first, substrings last
# Types whose values contain other types as substrings are processed first
PII_TYPE_ORDER: list[str] = [
    # Tier 1: Long, structured identifiers (contain substrings, never are substrings)
    "medical_record_number",           # UUIDs, very long
    "ssn",                             # 9 digits, structured
    "device_identifier",               # 14+ digits
    "vehicle_identifier",              # VINs (17 chars), plates
    "health_plan_beneficiary_number",  # AETNA-681277021 contains company name
    "account_number",                  # ACCT-12345 format
    "certificate_or_license_number",   # S99960000 format
    # Tier 2: Structured with special characters
    "email",                           # contains @ and person names
    "url",                             # contains http(s)://
    "ip_address",                      # dotted notation
    # Tier 3: Phone numbers (contain years as substrings)
    "phone_number",                    # 555-268-1985 contains "1985"
    "fax_number",                      # same pattern
    # Tier 4: Variable length (within-type length sort handles it)
    "person_name",                     # full names before partial
    "address",                         # full addresses before partial
    # Tier 5: Short/generic (likely to BE substrings of others)
    "biometric_identifier",            # unclear content
    "photographic_image",              # unclear content
    "date",                            # years like "1985" are substrings
    "other",                           # catch-all, always last
]


def _type_sort_key(pii_type: str) -> tuple[int, str]:
    """Return sort key for deterministic PII type ordering.

    Types in PII_TYPE_ORDER are sorted by their index.
    Unknown types are sorted after 'other', alphabetically.
    """
    try:
        return (PII_TYPE_ORDER.index(pii_type), pii_type)
    except ValueError:
        # Unknown type: after 'other' (index len), then alphabetically
        return (len(PII_TYPE_ORDER), pii_type)


class FormatterProtocol(Protocol):
    """Protocol for redaction formatters."""
    
    def get_tag(self, pii_type: str, value: str) -> str:
        """Get the redaction tag for a PII value."""
        ...
    
    def reset(self) -> None:
        """Reset formatter state."""
        ...


@dataclass
class RedactionResult:
    """Result of redact_text() with statistics."""
    text: str
    skipped_by_type: dict[str, int]


def load_document_with_encoding(input_path: Path) -> str:
    """Load a document with automatic encoding detection."""
    raw_bytes = input_path.read_bytes()
    
    if len(raw_bytes) >= 2:
        if raw_bytes[:2] == b'\xff\xfe':
            return raw_bytes.decode('utf-16-le')
        elif raw_bytes[:2] == b'\xfe\xff':
            return raw_bytes.decode('utf-16-be')
    
    try:
        return raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return raw_bytes.decode('utf-16-le')
        except UnicodeDecodeError:
            return raw_bytes.decode('latin-1', errors='replace')


def format_pii_tag(pii_type: str) -> str:
    """Convert PII type to tag format (e.g., 'person_name' -> '[PERSON_NAME]').
    
    This is the legacy function for backwards compatibility.
    For custom formats, use a RedactionFormatter instance instead.
    """
    return f"[{pii_type.upper()}]"


def make_word_boundary_pattern(value: str) -> re.Pattern[str]:
    """Create a regex pattern that matches value only at word boundaries.
    
    This prevents matching substrings within words (e.g., "MA" in "SUMMARY").
    """
    return re.compile(r'\b' + re.escape(value) + r'\b')


def redact_text(
    text: str,
    pii_entities: list[dict[str, Any]],
    source_name: str = "",
    formatter: FormatterProtocol | None = None,
) -> RedactionResult:
    """Redact PII entities from text by replacing exact string matches with tags.

    Entities are grouped by PII type, then sorted by value length (longest first)
    within each group. This prevents partial replacement issues and reduces false
    positive skip warnings.

    Args:
        text: The original text to redact.
        pii_entities: List of PII entity dictionaries with 'type' and 'value' keys.
        source_name: Optional identifier for logging purposes.
        formatter: Optional formatter for custom redaction tags. If None, uses
                   the default [PII_TYPE] format.

    Returns:
        RedactionResult containing the redacted text and skipped redaction stats.
        skipped_by_type only includes types where ALL entities were not found.
    """
    if not pii_entities or not text:
        return RedactionResult(text=text, skipped_by_type={})

    # Use default formatter if none provided
    if formatter is None:
        formatter = DefaultFormatter()

    # Group entities by PII type
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in pii_entities:
        pii_type = entity.get("type", "")
        if pii_type:
            groups[pii_type].append(entity)

    # Sort each group by value length (longest first)
    for pii_type in groups:
        groups[pii_type].sort(key=lambda e: len(e.get("value", "")), reverse=True)

    redacted_text = text
    total_replacements = 0
    skipped_by_type: dict[str, int] = {}

    # Track which values we've already processed globally to avoid double-replacement
    processed_values: set[str] = set()

    # Process each group
    for pii_type in sorted(groups.keys(), key=_type_sort_key):
        entities = groups[pii_type]
        successful_in_group = 0
        skipped_in_group = 0

        for entity in entities:
            value = entity.get("value", "")

            if not value:
                logger.warning(
                    "Empty value for %s entity in %s, skipping",
                    pii_type,
                    source_name,
                )
                continue

            # Skip if we've already processed this exact value
            if value in processed_values:
                continue
            processed_values.add(value)

            tag = formatter.get_tag(pii_type, value)

            pattern = make_word_boundary_pattern(value)
            occurrences = len(pattern.findall(redacted_text))

            if occurrences == 0:
                skipped_in_group += 1
                logger.debug(
                    "PII string %r (type=%s) not found in %s",
                    value,
                    pii_type,
                    source_name,
                )
                continue

            redacted_text = pattern.sub(tag, redacted_text)
            total_replacements += occurrences
            successful_in_group += 1

            logger.debug(
                "Redacted %s occurrence(s) of %r (type=%s) -> %s in %s",
                occurrences,
                value,
                pii_type,
                tag,
                source_name,
            )

        # Only track as skipped if ALL entities in the group failed
        if successful_in_group == 0 and skipped_in_group > 0:
            skipped_by_type[pii_type] = skipped_in_group
            logger.warning(
                "All %s %s entities not found in %s",
                skipped_in_group,
                pii_type,
                source_name or "document",
            )

    if total_replacements > 0:
        logger.info(
            "Redacted %s total PII occurrence(s) from %s",
            total_replacements,
            source_name or "document",
        )

    return RedactionResult(text=redacted_text, skipped_by_type=skipped_by_type)


def find_pii_positions(text: str, pii_entities: list[dict[str, Any]], source_name: str = "") -> list[dict[str, Any]]:
    """Find all occurrences of PII entities in text and return their positions."""
    if not pii_entities or not text:
        return []
    
    positions = []
    
    for entity in pii_entities:
        pii_type = entity.get("type", "")
        value = entity.get("value", "")
        
        if not value:
            logger.warning(
                "Empty value for %s entity in %s, skipping",
                pii_type,
                source_name,
            )
            continue
        
        # Use word boundaries to match whole words only (same as redact_text)
        pattern = make_word_boundary_pattern(value)
        for match in pattern.finditer(text):
            positions.append({
                "type": pii_type,
                "value": value,
                "start": match.start(),
                "end": match.end(),
            })
    
    return positions


def process_json_file(
    json_path: Path,
    output_dir: Path,
    output_json_dir: Path | None = None,
    formatter: FormatterProtocol | None = None,
) -> None:
    """Process a single JSON annotation file and create a redacted text file.
    
    Args:
        json_path: Path to the JSON file containing PII annotations.
        output_dir: Directory to write the redacted text file.
        output_json_dir: Optional directory to write the positions JSON file.
        formatter: Optional formatter for custom redaction tags.
    """
    try:
        with json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        
        source_path_str = data.get("source")
        if not source_path_str:
            logger.warning("No 'source' field found in %s, skipping", json_path)
            return
        
        source_path = Path(source_path_str)
        
        if not source_path.is_absolute():
            project_root = Path(__file__).parent
            source_path = project_root / source_path
        
        if not source_path.exists():
            logger.error("Source file not found: %s (from %s)", source_path, json_path)
            return
        
        original_text = load_document_with_encoding(source_path)
        response = data.get("response", {})
        pii_entities = response.get("pii_entities", [])
        
        if not pii_entities:
            logger.info("No PII entities found in %s", json_path)
        else:
            logger.info("Processing %s PII entities from %s", len(pii_entities), json_path)
        
        # Reset formatter state for each document to get fresh identifiers
        if formatter is not None:
            formatter.reset()
        
        redaction_result = redact_text(
            original_text,
            pii_entities,
            source_name=str(json_path),
            formatter=formatter,
        )
        redacted_text = redaction_result.text
        pii_positions = find_pii_positions(original_text, pii_entities, source_name=str(json_path))
        
        json_stem = json_path.stem
        if json_stem.endswith("_response"):
            output_stem = json_stem[:-9] + "_redacted"
            positions_stem = json_stem[:-9] + "_positions"
        else:
            output_stem = json_stem + "_redacted"
            positions_stem = json_stem + "_positions"
        
        output_path = output_dir / f"{output_stem}.txt"
        output_path.write_text(redacted_text, encoding="utf-8")
        logger.info("Redacted text saved to %s (%s entities processed)", output_path, len(pii_entities))
        
        if output_json_dir is not None:
            output_json_dir.mkdir(parents=True, exist_ok=True)
            positions_path = output_json_dir / f"{positions_stem}.json"
            positions_data = {"pii_entities": pii_positions}
            positions_path.write_text(json.dumps(positions_data, indent=2), encoding="utf-8")
            logger.info("PII positions JSON saved to %s (%s occurrences)", positions_path, len(pii_positions))
        
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        logger.error("Error processing %s: %s", json_path, exc)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments for standalone redaction."""
    parser = argparse.ArgumentParser(
        description="Redact PII from text files based on JSON annotation files.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("output"),
        help="Directory containing JSON annotation files (default: output/)",
    )
    parser.add_argument(
        "--output-text-dir",
        type=Path,
        default=None,
        help="Directory for redacted text files (default: <input-dir>-text/)",
    )
    parser.add_argument(
        "--output-json-dir",
        type=Path,
        default=None,
        help="Directory for positions JSON files (default: <input-dir>-json/)",
    )
    
    # Custom format options
    format_group = parser.add_argument_group("Custom Redaction Format")
    format_group.add_argument(
        "--custom",
        metavar="FORMAT_NAME",
        help="Use a saved custom redaction format by name.",
    )
    format_group.add_argument(
        "--define-format",
        metavar="TEMPLATE",
        help="Define a custom format template. Use {TYPE} for PII type and {ID} for "
             "unique identifier. Examples: '[REDACTED]', '[{TYPE}]', '**{TYPE}[{ID}]'",
    )
    format_group.add_argument(
        "--id-scheme",
        choices=["alpha", "numeric"],
        default="alpha",
        help="Identifier scheme for custom format: 'alpha' (A,B,C) or 'numeric' (1,2,3). Default: alpha",
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
        A RedactionFormatter if custom format is specified, None otherwise.
    """
    manager = RedactionFormatManager()
    
    # Load existing format by name
    if args.custom:
        fmt = manager.load(args.custom)
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
        
        return RedactionFormatter(fmt)
    
    # No custom format specified, use default
    return None


def main() -> None:
    """Main entry point: process all JSON files in the input directory."""
    args = parse_args()
    
    # Handle --list-formats
    if args.list_formats:
        manager = RedactionFormatManager()
        formats = manager.list_formats()
        if formats:
            print("Available custom formats:")
            for name in formats:
                try:
                    fmt = manager.load(name)
                    print(f"  {name}: {fmt.template} (id_scheme={fmt.id_scheme})")
                except Exception:
                    print(f"  {name}: (error loading)")
        else:
            print("No saved formats found. Create one with --define-format and --save-as.")
        return
    
    # Create formatter from args
    formatter = create_formatter_from_args(args)
    
    # Resolve directories
    project_root = Path(__file__).parent
    input_dir = args.input_dir
    if not input_dir.is_absolute():
        input_dir = project_root / input_dir
    
    output_text_dir = args.output_text_dir
    if output_text_dir is None:
        output_text_dir = input_dir.parent / f"{input_dir.name}-text"
    elif not output_text_dir.is_absolute():
        output_text_dir = project_root / output_text_dir
    
    output_json_dir = args.output_json_dir
    if output_json_dir is None:
        output_json_dir = input_dir.parent / f"{input_dir.name}-json"
    elif not output_json_dir.is_absolute():
        output_json_dir = project_root / output_json_dir
    
    if not input_dir.exists():
        logger.error("Input directory not found: %s", input_dir)
        return
    
    output_text_dir.mkdir(parents=True, exist_ok=True)
    output_json_dir.mkdir(parents=True, exist_ok=True)
    
    json_files = sorted(input_dir.glob("*.json"))
    
    if not json_files:
        logger.warning("No JSON files found in %s", input_dir)
        return
    
    logger.info("Processing %s JSON file(s) from %s", len(json_files), input_dir)
    
    for json_path in json_files:
        process_json_file(json_path, output_text_dir, output_json_dir, formatter=formatter)
    
    logger.info("Redaction complete. Redacted files saved to %s, positions JSON saved to %s", output_text_dir, output_json_dir)


if __name__ == "__main__":
    main()
