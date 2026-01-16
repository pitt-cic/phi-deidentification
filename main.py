"""Main module for processing documents with the Bedrock-backed PII agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

import logfire
from agent import AgentContext, AgentResponse, DetectionParameters, pii_agent
from agent.prompt import SYSTEM_PROMPT
from redact_pii import process_json_file

DEFAULT_PROMPT = (
    "Analyze the document text and identify all requested PII strings. "
)
DEFAULT_MAX_CHARS = 20_000

logger = logging.getLogger("pii_deidentification.main")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Bedrock-backed PII agent against a text document.",
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
        help="Override the default PII categories (space-separated list).",
    )
    parser.add_argument(
        "--max-entities",
        type=int,
        default=None,
        help="Maximum number of PII spans the agent should return.",
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
        help="Skip automatic PII redaction after processing (dataset mode only).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Maximum number of documents to process concurrently (default: 3).",
    )
    return parser.parse_args()

def load_document(input_path: Path) -> str:
    if str(input_path) == "-":
        return sys.stdin.read()
    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(f"Input path does not exist or is not a file: {input_path}")
    
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

def validate_document_length(document_text: str, max_chars: int) -> None:
    if not document_text.strip():
        raise ValueError("Document is empty; nothing to analyze.")
    if max_chars > 0 and len(document_text) > max_chars:
        raise ValueError(f"Document length {len(document_text)} exceeds limit of {max_chars} characters.")

def build_detection_params(
    pii_types: Sequence[str] | None,
    max_entities: int | None,
) -> DetectionParameters:
    kwargs: dict[str, Any] = {}
    if pii_types:
        kwargs["pii_types"] = [value.lower() for value in pii_types if value.strip()]
    if max_entities is not None:
        kwargs["max_entities"] = max_entities
    return DetectionParameters(**kwargs)

def build_response_payload(
    response: AgentResponse,
    source_name: str,
    language: str,
    detection: DetectionParameters,
    raw_response: bool = False,
) -> dict[str, Any]:
    """Build the output payload, either raw response or wrapped with metadata."""
    if raw_response:
        return response.model_dump()
    return {
        "source": source_name,
        "language": language,
        "pii_types": detection.pii_types,
        "max_entities": detection.max_entities,
        "response": response.model_dump(),
    }

def build_prompt_with_document(prompt: str, document_text: str) -> str:
    """Build the full prompt with document text delimited."""
    document_delimiter = "=" * 80
    return f"{prompt}\n\n{document_delimiter}\nDocument text to analyze:\n{document_delimiter}\n{document_text}\n{document_delimiter}"

async def process_document(
    document_text: str,
    *,
    source_name: str,
    detection: DetectionParameters,
    language: str = "en",
    prompt: str = DEFAULT_PROMPT,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> AgentResponse:
    validate_document_length(document_text, max_chars)
    context = AgentContext(
        document_text=document_text,
        source_name=source_name,
        language=language,
        detection=detection,
    )

    full_prompt = build_prompt_with_document(prompt, document_text)
    
    pii_types_str = ", ".join(detection.pii_types)
    limit = detection.max_entities or "no-limit"
    detection_scope = (
        f"<detection_scope>"
        f"source={source_name}; "
        f"pii_types={pii_types_str}; "
        f"max_entities={limit}"
        f"</detection_scope>"
    )
    system_instructions = f"{SYSTEM_PROMPT}\n\n{detection_scope}"
    
    with logfire.span('pii_detection', 
                      source=source_name,
                      document_length=len(document_text)) as span:
        span.set_attribute('system_instructions', system_instructions)
        span.set_attribute('user_prompt', full_prompt)
        
        result = await pii_agent.run(full_prompt, deps=context)
        response: AgentResponse = result.output
        
        span.set_attribute('response', response.model_dump())
        span.set_attribute('entities_count', len(response.pii_entities))
        span.set_attribute('needs_review', response.needs_review)
    
    logger.info(
        "Processed '%s': %s entities (needs_review=%s)",
        source_name,
        len(response.pii_entities),
        response.needs_review,
    )
    return response

async def process_single_document(
    doc_path: Path,
    semaphore: asyncio.Semaphore,
    *,
    detection: DetectionParameters,
    language: str,
    max_chars: int,
    raw_response: bool,
    output_dir: Path,
) -> tuple[bool, Path, str | None]:
    """Process a single document with semaphore-controlled concurrency.
    
    Returns:
        Tuple of (success, doc_path, error_message or None)
    """
    async with semaphore:
        try:
            document_text = load_document(doc_path)
            response = await process_document(
                document_text,
                source_name=str(doc_path),
                detection=detection,
                language=language,
                max_chars=max_chars,
            )
            payload = build_response_payload(response, str(doc_path), language, detection, raw_response)
            output_file = output_dir / f"{doc_path.stem}_response.json"
            output_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            logger.info("Wrote result for '%s' to '%s'.", doc_path.name, output_file)
            return (True, doc_path, None)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to process '%s': %s", doc_path, exc)
            return (False, doc_path, str(exc))


async def process_dataset(
    dataset_dir: Path,
    *,
    detection: DetectionParameters,
    language: str,
    max_chars: int,
    raw_response: bool,
    output_dir: Path,
    auto_redact: bool = True,
    concurrency: int = 3,
) -> None:
    if not dataset_dir.exists() or not dataset_dir.is_dir():
        raise FileNotFoundError(f"Dataset directory does not exist: {dataset_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    documents = sorted(path for path in dataset_dir.glob("*.txt") if path.is_file())
    if not documents:
        raise ValueError(f"No .txt files found in dataset directory: {dataset_dir}")

    logger.info("Processing %d documents with concurrency=%d", len(documents), concurrency)
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        process_single_document(
            doc_path,
            semaphore,
            detection=detection,
            language=language,
            max_chars=max_chars,
            raw_response=raw_response,
            output_dir=output_dir,
        )
        for doc_path in documents
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    processed = 0
    failed = 0
    for result in results:
        if isinstance(result, Exception):
            failed += 1
            logger.error("Unexpected error during processing: %s", result)
        else:
            success, doc_path, error = result
            if success:
                processed += 1
            else:
                failed += 1

    total = len(documents)
    logger.info(
        "Dataset processing complete: %s/%s succeeded (%s failures). Results saved in %s",
        processed,
        total,
        failed,
        output_dir,
    )
    
    if auto_redact and processed > 0:
        logger.info("Starting automatic PII redaction...")
        output_text_dir = output_dir.parent / f"{output_dir.name}-text"
        output_json_dir = output_dir.parent / f"{output_dir.name}-json"
        output_text_dir.mkdir(parents=True, exist_ok=True)
        output_json_dir.mkdir(parents=True, exist_ok=True)
        
        json_files = sorted(output_dir.glob("*.json"))
        for json_path in json_files:
            process_json_file(json_path, output_text_dir, output_json_dir)
        
        logger.info("Redaction complete. Redacted files saved to %s, positions JSON saved to %s", output_text_dir, output_json_dir)

async def run_cli() -> None:
    args = parse_args()
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
