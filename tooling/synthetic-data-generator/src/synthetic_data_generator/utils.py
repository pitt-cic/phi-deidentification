"""General utility functions for file handling, S3 paths, and data formatting."""

import glob
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def is_s3_path(path: str | None) -> bool:
    """
    Determine if the given path is an S3 path.

    Args:
        path (str): The path to be checked.

    Returns:
        bool: True if the path is an S3 path, False otherwise.

    Raises:
        TypeError: If the input is not a string.
    """
    if path is None or path.strip() == "":
        return False

    return path.startswith("s3://")

def parse_s3_path(s3_path: str) -> tuple[str, str]:
    """
    Parse an S3 path into bucket and prefix.

    Args:
        s3_path (str): The S3 path to be parsed.

    Returns:
        tuple: A tuple containing the bucket and prefix.

    Raises:
        ValueError: If the input is not a valid S3 path.
    """
    parsed = urlparse(s3_path)
    bucket = parsed.netloc
    prefix = parsed.path.lstrip('/')
    return bucket, prefix

def list_local_files(path: str, pattern: str | None = None, limit: int | None = None) -> list[Path]:
    """
    List all files in a local directory, optionally filtering by extensions.

    Args:
        path (str): The directory path to list files from.
        pattern (str | None): The glob pattern to filter files.
        limit (int | None): The maximum number of files to return.

    Returns:
        list[Path]: A list of file paths.
    """
    # If path is a file, return it as a list
    if Path(path).is_file():
        return [Path(path)]

    files = (
        glob.glob(f"{path.rstrip('/')}/{pattern.lstrip('/')}")
        if pattern
        else glob.glob(f"{path.rstrip('/')}/*")
    )
    files = sorted(files)

    file_paths = []
    for f in files:
        if Path(f).is_file():
            file_paths.append(Path(f))
            if limit and len(file_paths) >= limit:
                break

    return file_paths

def round_and_to_str(value: float | int | str | None = None) -> str:
    """Round a numeric value and convert to string, or return empty string if falsy."""
    if not value:
        return ''
    if isinstance(value, str):
        return value

    return str(round(value))

def strip_digits(value: str | None) -> str:
    """Remove all digits from a string."""
    if not value:
        return ''
    return re.sub(r'\d', '', value)

def human_readable_datetime(date_str: str) -> str:
    """Convert an ISO datetime string to a human-readable format."""
    if not date_str:
        return ''
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%Y-%m-%d, %I:%M %p")
    except Exception:
        return date_str


def should_include_in_llm_context(value, allow_zero_if_number_field: bool = False) -> bool:
    """Determine if a value should be included in LLM context (non-empty, non-zero)."""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, (int, float)) and value == 0 and not allow_zero_if_number_field:
        return False
    return True
