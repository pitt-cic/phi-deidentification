import glob
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


from src.config import NoteType


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

def get_note_types(type_str: str) -> list[NoteType | str]:
    """
    Get a list of note types from a string. Skips unknown types.

    Args:
        type_str (str): A comma-separated string of note types.

    Returns:
        list[NoteType | str]: A list of note types.
    """
    if type_str.lower() == "all":
        return list(NoteType)

    type_map = {
        "emergency_dept": NoteType.EMERGENCY_DEPT,
        "discharge_summary": NoteType.DISCHARGE_SUMMARY,
        "progress_note": NoteType.PROGRESS_NOTE,
        "radiology_report": NoteType.RADIOLOGY_REPORT,
        "telehealth_consult": NoteType.TELEHEALTH_CONSULT,
    }

    types = []
    for t in type_str.lower().split(","):
        t = t.strip()
        if t in type_map:
            types.append(type_map[t])
        else:
            print(f"Warning: unknown type {t}, skipping")

    return types

def round_and_to_str(value: float | int | str | None = None) -> str:
    if not value:
        return ''
    if isinstance(value, str):
        return value

    return str(round(value))

def strip_digits(value: str | None) -> str:
    if not value:
        return ''
    return re.sub(r'\d', '', value)

def human_readable_datetime(date_str: str) -> str:
    if not date_str:
        return ''
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%Y-%m-%d, %I:%M %p")
    # Return the original string if not a valid date
    except Exception:
        return date_str
