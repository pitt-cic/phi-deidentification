"""Utility functions for model operations."""

from .note_models import NoteType


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