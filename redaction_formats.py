"""Custom redaction format system for PII de-identification."""

from __future__ import annotations

import json
import logging
import string
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger("pii_deidentification.redaction_formats")

DEFAULT_FORMATS_DIR = Path(__file__).parent / "redaction_formats"
IdScheme = Literal["alpha", "numeric"]


@dataclass
class RedactionFormat:
    """Configuration for a custom redaction format.
    
    Templates can use optional placeholders:
    - {TYPE}: PII type (NAME, DATE, etc.)
    - {ID}: Unique identifier (A, B, C or 1, 2, 3)
    
    Examples: "[REDACTED]", "[{TYPE}]", "**{TYPE}[{ID}]"
    """
    template: str
    id_scheme: IdScheme = "alpha"
    name: str | None = None
    created: str | None = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "template": self.template,
            "id_scheme": self.id_scheme,
            "created": self.created or datetime.now(timezone.utc).isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> RedactionFormat:
        return cls(
            template=data["template"],
            id_scheme=data.get("id_scheme", "alpha"),
            name=data.get("name"),
            created=data.get("created"),
        )


class RedactionFormatManager:
    """Manages loading and saving of redaction format configurations."""
    
    def __init__(self, formats_dir: Path | None = None) -> None:
        self.formats_dir = formats_dir or DEFAULT_FORMATS_DIR
    
    def save(self, fmt: RedactionFormat) -> Path:
        """Save a format configuration. Raises ValueError if format has no name."""
        if not fmt.name:
            raise ValueError("Format must have a name to be saved")
        
        self.formats_dir.mkdir(parents=True, exist_ok=True)
        path = self.formats_dir / f"{fmt.name}.json"
        path.write_text(json.dumps(fmt.to_dict(), indent=2), encoding="utf-8")
        logger.info("Saved format '%s' to %s", fmt.name, path)
        return path
    
    def load(self, name: str) -> RedactionFormat:
        """Load a format configuration. Raises FileNotFoundError if not found."""
        path = self.formats_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"No format found with name '{name}'")
        
        data = json.loads(path.read_text(encoding="utf-8"))
        logger.info("Loaded format '%s' from %s", name, path)
        return RedactionFormat.from_dict(data)
    
    def list_formats(self) -> list[str]:
        """List all available format names."""
        if not self.formats_dir.exists():
            return []
        return sorted(p.stem for p in self.formats_dir.glob("*.json"))


class RedactionFormatter:
    """Generates unique redaction tags with consistent value tracking.
    
    Tracks unique PII values per type and assigns consistent identifiers:
    - "John" (person_name) → **NAME[A]
    - "Jane" (person_name) → **NAME[B]
    - "John" again → **NAME[A] (same ID)
    """

    TYPE_ABBREV = {
        "person_name": "NAME",
        "address": "ADDR",
        "date": "DATE",
        "phone_number": "PHONE",
        "fax_number": "FAX",
        "email": "EMAIL",
        "ssn": "SSN",
        "social_security_number": "SSN",
        "medical_record_number": "MRN",
        "health_plan_beneficiary_number": "HPBN",
        "account_number": "ACCOUNT",
        "certificate_or_license_number": "LICENSE",
        "vehicle_identifier": "VIN",
        "device_identifier": "DEVICE",
        "url": "URL",
        "ip_address": "IP",
        "biometric_identifier": "BIOMETRIC",
        "photographic_image": "PHOTO",
        "age": "AGE",
        "other": "OTHER",
    }
    
    def __init__(self, fmt: RedactionFormat) -> None:
        self.format = fmt
        self._value_to_id: dict[tuple[str, str], str] = {}
        self._type_counters: dict[str, int] = {}
    
    def get_tag(self, pii_type: str, value: str) -> str:
        """Get the redaction tag for a PII value."""
        template = self.format.template
        
        # No placeholders = static template
        if "{TYPE}" not in template and "{ID}" not in template:
            return template
        
        type_display = self.TYPE_ABBREV.get(pii_type.lower(), pii_type.upper())
        
        identifier = ""
        if "{ID}" in template:
            key = (pii_type.lower(), value)
            if key not in self._value_to_id:
                self._value_to_id[key] = self._next_id(pii_type.lower())
            identifier = self._value_to_id[key]
        
        return template.format(TYPE=type_display, ID=identifier)
    
    def _next_id(self, pii_type: str) -> str:
        """Generate the next identifier for a PII type."""
        count = self._type_counters.get(pii_type, 0)
        self._type_counters[pii_type] = count + 1
        
        if self.format.id_scheme == "numeric":
            return str(count + 1)
        
        # Alpha: A, B, ..., Z, AA, AB, ...
        result, n = [], count + 1
        while n > 0:
            n -= 1
            result.append(string.ascii_uppercase[n % 26])
            n //= 26
        return "".join(reversed(result))
    
    def reset(self) -> None:
        """Reset tracking state (call between documents)."""
        self._value_to_id.clear()
        self._type_counters.clear()


class DefaultFormatter:
    """Default formatter producing [TYPE] tags without unique IDs."""
    
    @staticmethod
    def get_tag(pii_type: str, value: str) -> str:
        return f"[{pii_type.upper()}]"
    
    def reset(self) -> None:
        pass
