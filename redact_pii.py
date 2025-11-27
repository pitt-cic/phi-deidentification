"""Script to redact PII from text files based on JSON annotation files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("pii_deidentification.redact")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

def format_pii_tag(pii_type: str) -> str:
    """Convert PII type to tag format (e.g., 'person_name' -> '[PERSON_NAME]')."""
    return f"[{pii_type.upper()}]"

def redact_text(text: str, pii_entities: list[dict[str, Any]], source_name: str = "") -> str:
    """Redact PII entities from text by replacing exact string matches with tags.
    
    Args:
        text: The original text to redact
        pii_entities: List of PII entity dicts with 'type', 'value', 'reason', and 'confidence' keys
        source_name: Optional source name for logging warnings
        
    Returns:
        The redacted text with PII replaced by tags
    """
    if not pii_entities:
        return text
    
    if not text:
        return text
    
    redacted_text = text
    total_replacements = 0
    
    # Sort entities by value length (longest first) to handle cases where one PII string
    # is a substring of another. This ensures we replace "John Smith" before "John".
    sorted_entities = sorted(pii_entities, key=lambda e: len(e.get("value", "")), reverse=True)
    
    for entity in sorted_entities:
        pii_type = entity.get("type", "")
        value = entity.get("value", "")
        reason = entity.get("reason", "")
        confidence = entity.get("confidence", "unknown")
        tag = format_pii_tag(pii_type)
        
        # Skip if value is empty
        if not value:
            logger.warning(
                "Empty value for %s entity in %s, skipping",
                pii_type,
                source_name,
            )
            continue
        
        # Count occurrences of this string in the text
        occurrences = redacted_text.count(value)
        
        if occurrences == 0:
            logger.warning(
                "PII string %r (type=%s, confidence=%s, reason=%s) not found in %s, skipping",
                value,
                pii_type,
                confidence,
                reason,
                source_name,
            )
            continue
        
        # Replace all occurrences of the exact string
        redacted_text = redacted_text.replace(value, tag)
        total_replacements += occurrences
        
        logger.debug(
            "Redacted %s occurrence(s) of %r (type=%s, confidence=%s) in %s",
            occurrences,
            value,
            pii_type,
            confidence,
            source_name,
        )
    
    if total_replacements > 0:
        logger.info(
            "Redacted %s total PII occurrence(s) from %s",
            total_replacements,
            source_name or "document",
        )
    
    return redacted_text

def find_pii_positions(text: str, pii_entities: list[dict[str, Any]], source_name: str = "") -> list[dict[str, Any]]:
    """Find all occurrences of PII entities in text and return their positions.
    
    Args:
        text: The original text to search
        pii_entities: List of PII entity dicts with 'type', 'value', 'reason', and 'confidence' keys
        source_name: Optional source name for logging warnings
        
    Returns:
        List of dicts with 'type', 'value', 'start', and 'end' keys for each occurrence
    """
    if not pii_entities or not text:
        return []
    
    positions = []
    
    for entity in pii_entities:
        pii_type = entity.get("type", "")
        value = entity.get("value", "")
        
        # Skip if value is empty
        if not value:
            logger.warning(
                "Empty value for %s entity in %s, skipping",
                pii_type,
                source_name,
            )
            continue
        
        # Find all occurrences of this value in the text
        start_pos = 0
        while True:
            pos = text.find(value, start_pos)
            if pos == -1:
                break
            
            # Add position entry for this occurrence
            positions.append({
                "type": pii_type,
                "value": value,
                "start": pos,
                "end": pos + len(value),
            })
            
            # Move search position forward
            start_pos = pos + 1
    
    return positions

def process_json_file(json_path: Path, output_dir: Path, output_json_dir: Path | None = None) -> None:
    """Process a single JSON annotation file and create a redacted text file.
    
    Args:
        json_path: Path to the JSON annotation file
        output_dir: Directory where redacted text files will be saved
        output_json_dir: Optional directory where positions JSON files will be saved
    """
    try:
        # Load JSON file
        with json_path.open(encoding="utf-8") as f:
            data = json.load(f)
        
        # Extract source file path
        source_path_str = data.get("source")
        if not source_path_str:
            logger.warning("No 'source' field found in %s, skipping", json_path)
            return
        
        source_path = Path(source_path_str)
        
        # Resolve relative paths relative to project root
        if not source_path.is_absolute():
            project_root = Path(__file__).parent
            source_path = project_root / source_path
        
        # Load original text file
        if not source_path.exists():
            logger.error("Source file not found: %s (from %s)", source_path, json_path)
            return
        
        original_text = source_path.read_text(encoding="utf-8")
        
        # Extract PII entities from response
        response = data.get("response", {})
        pii_entities = response.get("pii_entities", [])
        
        if not pii_entities:
            logger.info("No PII entities found in %s", json_path)
        else:
            logger.info("Processing %s PII entities from %s", len(pii_entities), json_path)
        
        # Redact the text using string-based matching
        redacted_text = redact_text(original_text, pii_entities, source_name=str(json_path))
        
        # Find PII positions for JSON output
        pii_positions = find_pii_positions(original_text, pii_entities, source_name=str(json_path))
        
        # Generate output filename
        # e.g., synthetic_note_001_original_response.json -> synthetic_note_001_original_redacted.txt
        json_stem = json_path.stem  # synthetic_note_001_original_response
        if json_stem.endswith("_response"):
            output_stem = json_stem[:-9] + "_redacted"  # synthetic_note_001_original_redacted
            positions_stem = json_stem[:-9] + "_positions"  # synthetic_note_001_original_positions
        else:
            output_stem = json_stem + "_redacted"
            positions_stem = json_stem + "_positions"
        
        output_path = output_dir / f"{output_stem}.txt"
        
        # Save redacted text
        output_path.write_text(redacted_text, encoding="utf-8")
        logger.info("Redacted text saved to %s (%s entities processed)", output_path, len(pii_entities))
        
        # Save positions JSON if output_json_dir is provided
        if output_json_dir is not None:
            output_json_dir.mkdir(parents=True, exist_ok=True)
            positions_path = output_json_dir / f"{positions_stem}.json"
            positions_data = {"pii_entities": pii_positions}
            positions_path.write_text(json.dumps(positions_data, indent=2), encoding="utf-8")
            logger.info("PII positions JSON saved to %s (%s occurrences)", positions_path, len(pii_positions))
        
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        logger.error("Error processing %s: %s", json_path, exc)

def main() -> None:
    """Main entry point: process all JSON files in output/ directory."""
    project_root = Path(__file__).parent
    output_dir = project_root / "output"
    output_text_dir = project_root / "output-text"
    output_json_dir = project_root / "output-json"
    
    if not output_dir.exists():
        logger.error("Output directory not found: %s", output_dir)
        return
    
    # Create output directories if they don't exist
    output_text_dir.mkdir(parents=True, exist_ok=True)
    output_json_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all JSON files in output directory
    json_files = sorted(output_dir.glob("*.json"))
    
    if not json_files:
        logger.warning("No JSON files found in %s", output_dir)
        return
    
    logger.info("Processing %s JSON file(s) from %s", len(json_files), output_dir)
    
    for json_path in json_files:
        process_json_file(json_path, output_text_dir, output_json_dir)
    
    logger.info("Redaction complete. Redacted files saved to %s, positions JSON saved to %s", output_text_dir, output_json_dir)

if __name__ == "__main__":
    main()

