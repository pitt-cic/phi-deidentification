"""Main module for processing documents with the Bedrock-backed PHI agent."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

import logfire
from agent import AgentResponse, CompactAgentResponse, DetectionParameters, pii_agent, expand_compact_response
from pydantic_ai.usage import RunUsage
from .redaction import FormatterProtocol, process_json_file
from .constants import DEFAULT_PROMPT, DEFAULT_MAX_CHARS

logger = logging.getLogger("phi_deidentification.main")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

def load_document(input_path: Path) -> str:
    """Load document text from file with automatic encoding detection.

    Supports UTF-8, UTF-16-LE, UTF-16-BE, and Latin-1 encodings.
    Use '-' as input_path to read from stdin.

    Args:
        input_path: Path to text file, or '-' for stdin.

    Returns:
        Document text content.

    Raises:
        FileNotFoundError: If input_path does not exist.
    """
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
    """Validate document is non-empty and within length limit.

    Args:
        document_text: The document text to validate.
        max_chars: Maximum allowed character count (0 disables limit).

    Raises:
        ValueError: If document is empty or exceeds max_chars.
    """
    if not document_text.strip():
        raise ValueError("Document is empty; nothing to analyze.")
    if max_chars > 0 and len(document_text) > max_chars:
        raise ValueError(f"Document length {len(document_text)} exceeds limit of {max_chars} characters.")

def build_detection_params(
    pii_types: Sequence[str] | None,
    max_entities: int | None,
) -> DetectionParameters:
    """Build DetectionParameters from optional overrides.

    Args:
        pii_types: Optional list of PHI types to detect.
        max_entities: Optional maximum number of entities to return.

    Returns:
        DetectionParameters instance with specified or default values.
    """
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
    """Build the output payload, either raw response or wrapped with metadata.

    Args:
        response: The agent response containing detected PHI entities.
        source_name: Identifier for the document source.
        language: Document language code.
        detection: PHI detection parameters used for the request.
        raw_response: If True, return only the response model dump;
            otherwise wrap with metadata.

    Returns:
        Dictionary containing either the raw response or a wrapped payload
        with source, language, detection parameters, and response data.
    """
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
    """Build the full prompt with document text delimited.

    Args:
        prompt: The base prompt instructions for PHI detection.
        document_text: The document text to analyze.

    Returns:
        Combined prompt string with document text wrapped in XML-style
        <document> tags.
    """
    return f"{prompt}\n\nDocument text to analyze:\n<document>\n{document_text}\n</document>"

async def process_document(
    document_text: str,
    *,
    source_name: str,
    detection: DetectionParameters,
    language: str = "en",
    prompt: str = DEFAULT_PROMPT,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> AgentResponse:
    """Process a document through the PHI detection agent.

    Args:
        document_text: Text content to analyze.
        source_name: Identifier for logging and tracing.
        detection: PHI detection parameters.
        language: Document language code (default: 'en').
        prompt: Custom prompt override.
        max_chars: Maximum document length.

    Returns:
        AgentResponse containing detected PHI entities.

    Raises:
        ValueError: If document is empty or exceeds max_chars.
    """
    validate_document_length(document_text, max_chars)

    full_prompt = build_prompt_with_document(prompt, document_text)
    
    usage = RunUsage()
    
    with logfire.span('pii_detection', 
                      source=source_name,
                      document_length=len(document_text)) as span:
        span.set_attribute('user_prompt', full_prompt)
        
        result = await pii_agent.run(full_prompt, usage=usage)
        compact_response: CompactAgentResponse = result.output
        response: AgentResponse = expand_compact_response(compact_response)
        
        span.set_attribute('response', response.model_dump())
        span.set_attribute('compacted_response', response.compacted.model_dump() if response.compacted else None)
        span.set_attribute('entities_count', len(response.pii_entities))
        span.set_attribute('input_tokens', usage.input_tokens if usage else 0)
        span.set_attribute('output_tokens', usage.output_tokens if usage else 0)
        span.set_attribute('cache_read_tokens', usage.cache_read_tokens if usage else 0)
        span.set_attribute('cache_write_tokens', usage.cache_write_tokens if usage else 0)
        span.set_attribute('total_tokens', usage.total_tokens if usage else 0)
    
    logger.info(
        "Processed '%s': %s entities - Tokens: input=%s, output=%s, total=%s",
        source_name,
        len(response.pii_entities),
        usage.input_tokens if usage else 0,
        usage.output_tokens if usage else 0,
        usage.total_tokens if usage else 0,
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

    Args:
        doc_path: Path to the document file to process.
        semaphore: Asyncio semaphore for controlling concurrency.
        detection: PHI detection parameters.
        language: Document language code.
        max_chars: Maximum document length allowed.
        raw_response: Whether to use raw response format without metadata.
        output_dir: Directory to write the JSON output file.

    Returns:
        Tuple of (success, doc_path, error_message or None).
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
    formatter: FormatterProtocol | None = None,
) -> None:
    """Process a dataset of documents through the PHI agent.
    
    Args:
        dataset_dir: Directory containing .txt files to process.
        detection: PHI detection parameters.
        language: Document language code.
        max_chars: Maximum document length.
        raw_response: Whether to use raw response format.
        output_dir: Directory for JSON output files.
        auto_redact: Whether to automatically redact after processing.
        concurrency: Maximum concurrent document processing.
        formatter: Optional custom redaction formatter.
    """
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
        logger.info("Starting automatic PHI redaction...")
        output_text_dir = output_dir.parent / f"{output_dir.name}-text"
        output_json_dir = output_dir.parent / f"{output_dir.name}-json"
        output_text_dir.mkdir(parents=True, exist_ok=True)
        output_json_dir.mkdir(parents=True, exist_ok=True)
        
        json_files = sorted(output_dir.glob("*.json"))
        for json_path in json_files:
            process_json_file(json_path, output_text_dir, output_json_dir, formatter=formatter)
        
        logger.info("Redaction complete. Redacted files saved to %s, positions JSON saved to %s", output_text_dir, output_json_dir)
