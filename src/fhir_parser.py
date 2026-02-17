"""FHIR Bundle parser for extracting patient data and clinical context."""
import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import jmespath
import re
from enum import StrEnum

from .utils import strip_digits, round_and_to_str, human_readable_datetime

class ExtensionURL(StrEnum):
    US_CORE_RACE = 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-race'
    US_CORE_ETHNICITY = 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity'
    MOTHERS_MAIDEN_NAME = 'http://hl7.org/fhir/StructureDefinition/patient-mothersMaidenName'
    BIRTH_PLACE = 'http://hl7.org/fhir/StructureDefinition/patient-birthPlace'
    DISABILITY_ADJUSTED_LIFE_YEARS = 'http://synthetichealth.github.io/synthea/disability-adjusted-life-years'
    QUALITY_ADJUSTED_LIFE_YEARS = 'http://synthetichealth.github.io/synthea/quality-adjusted-life-years'

class MaritalStatus(StrEnum):
    ANNULLED = 'A'
    DIVORCED = 'D'
    INTERLOCUTORY = 'I'
    LEGALLY_SEPARATED = 'L'
    MARRIED = 'M'
    COMMON_LAW = 'C'
    POLYGAMOUS = 'P'
    DOMESTIC_PARTNER = 'T'
    UNMARRIED = 'U'
    NEVER_MARRIED = 'S'
    WIDOWED = 'W'

    @classmethod
    def from_code(cls, letter: str | None) -> str:
        if not letter:
            return ''
        for status in cls:
            if status.value[0] == letter:
                return ' '.join(status.name.split('_')).title()
        return ''


@dataclass
class PatientData:
    """Extracted patient demographics and identifiers."""
    # Core identifiers
    id: str = ""
    mrn: str = ""
    ssn: str = ""
    drivers_license: str = ""
    passport: str = ""

    # Demographics
    first_name: str = ""
    nicknames: str = ""
    last_name: str = ""
    full_name: str = ""
    prefix: str = ""
    gender: str = ""
    birth_date: str = ""
    age: int = 0
    deceased_date: Optional[str] = None

    # Contact info
    phone: str = ""
    email: str = ""
    fax: str = ""
    address_line: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = ""
    address_city_and_state: str = ""
    address_state_and_country: str = ""
    address_city_state_and_country: str = ""
    full_address: str = ""

    # Additional demographics
    race: str = ""
    ethnicity: str = ""
    marital_status: str = ""
    # birth_place: str = ""
    birth_city: str = ""
    birth_state: str = ""
    birth_country: str = ""
    birth_city_and_state: str = ""
    birth_state_and_country: str = ""
    birth_city_state_and_country: str = ""
    birth_city_and_country: str = ""
    mothers_maiden_name: str = ""

    # Additional information
    disability_adjusted_life_years: str = ""
    quality_adjusted_life_years: str = ""
    health_plan_id: str = ""
    account_number: str = ""
    vehicle_id: str = ""
    license_plate: str = ""
    ip_address: str = ""
    patient_portal_url: str = ""

    # Emergency contact
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""
    emergency_contact_relationship: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_context_string(self) -> str:
        """
        Convert patient data to context string for LLM.

        Returns flat list of non-empty fields in 'Label: Value' format.
        Skips fields that are None, empty string, or 0 (except age).
        """
        lines = []

        # Helper to check if field should be included
        def should_include(value, field_name: str) -> bool:
            if value is None or value == "":
                return False
            # Allow age=0 (newborns), but skip other 0 values
            if value == 0 and field_name != "age":
                return False
            return True

        # Add all patient fields in logical order
        if should_include(self.id, "id"):
            lines.append(f"Patient ID: {self.id}")
        if should_include(self.mrn, "mrn"):
            lines.append(f"MRN: {self.mrn}")
        if should_include(self.first_name, "first_name"):
            lines.append(f"First Name: {self.first_name}")
        if should_include(self.last_name, "last_name"):
            lines.append(f"Last Name: {self.last_name}")
        if should_include(self.full_name, "full_name"):
            lines.append(f"Full Name: {self.full_name}")
        if should_include(self.prefix, "prefix"):
            lines.append(f"Prefix: {self.prefix}")
        if should_include(self.nicknames, "nicknames"):
            lines.append(f"Nicknames: {self.nicknames}")
        if should_include(self.birth_date, "birth_date"):
            lines.append(f"Date of Birth: {self.birth_date}")
        if should_include(self.age, "age"):
            lines.append(f"Age: {self.age}")
        if should_include(self.deceased_date, "deceased_date"):
            lines.append(f"Deceased Date: {self.deceased_date}")
        if should_include(self.gender, "gender"):
            lines.append(f"Gender: {self.gender}")
        if should_include(self.race, "race"):
            lines.append(f"Race: {self.race}")
        if should_include(self.ethnicity, "ethnicity"):
            lines.append(f"Ethnicity: {self.ethnicity}")
        if should_include(self.marital_status, "marital_status"):
            lines.append(f"Marital Status: {self.marital_status}")
        if should_include(self.ssn, "ssn"):
            lines.append(f"SSN: {self.ssn}")
        if should_include(self.drivers_license, "drivers_license"):
            lines.append(f"Driver's License: {self.drivers_license}")
        if should_include(self.passport, "passport"):
            lines.append(f"Passport: {self.passport}")
        if should_include(self.phone, "phone"):
            lines.append(f"Phone: {self.phone}")
        if should_include(self.address_line, "address_line"):
            lines.append(f"Address: {self.address_line}")
        if should_include(self.city, "city"):
            lines.append(f"City: {self.city}")
        if should_include(self.state, "state"):
            lines.append(f"State: {self.state}")
        if should_include(self.zip_code, "zip_code"):
            lines.append(f"ZIP Code: {self.zip_code}")
        if should_include(self.country, "country"):
            lines.append(f"Country: {self.country}")
        if should_include(self.full_address, "full_address"):
            lines.append(f"Full Address: {self.full_address}")
        if should_include(self.birth_city, "birth_city"):
            lines.append(f"Birth City: {self.birth_city}")
        if should_include(self.birth_state, "birth_state"):
            lines.append(f"Birth State: {self.birth_state}")
        if should_include(self.birth_country, "birth_country"):
            lines.append(f"Birth Country: {self.birth_country}")
        if should_include(self.mothers_maiden_name, "mothers_maiden_name"):
            lines.append(f"Mother's Maiden Name: {self.mothers_maiden_name}")
        if should_include(self.disability_adjusted_life_years, "disability_adjusted_life_years"):
            lines.append(f"Disability Adjusted Life Years: {self.disability_adjusted_life_years}")
        if should_include(self.quality_adjusted_life_years, "quality_adjusted_life_years"):
            lines.append(f"Quality Adjusted Life Years: {self.quality_adjusted_life_years}")
        if should_include(self.emergency_contact_name, "emergency_contact_name"):
            lines.append(f"Emergency Contact Name: {self.emergency_contact_name}")
        if should_include(self.emergency_contact_phone, "emergency_contact_phone"):
            lines.append(f"Emergency Contact Phone: {self.emergency_contact_phone}")

        return "\n".join(lines)

    """
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "mrn": self.mrn,
            "ssn": self.ssn,
            "drivers_license": self.drivers_license,
            "passport": self.passport,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "prefix": self.prefix,
            "gender": self.gender,
            "birth_date": self.birth_date,
            "age": self.age,
            "deceased_date": self.deceased_date,
            "phone": self.phone,
            "address_line": self.address_line,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "country": self.country,
            "full_address": self.full_address,
            "race": self.race,
            "ethnicity": self.ethnicity,
            "marital_status": self.marital_status,
            # "birth_place": self.birth_place,
            "birth_city": self.birth_city,
            "birth_state": self.birth_state,
            "birth_country": self.birth_country,
            "mothers_maiden_name": self.mothers_maiden_name,
        }
    """

@dataclass
class EncounterData:
    """Extracted encounter information."""
    id: str = ""
    # type_code: str = ""
    type_display: str = ""
    encounter_class: str = ""
    # reason_code: str = ""
    reason_display: str = ""
    start_datetime: str = ""
    end_datetime: str = ""
    # provider_id: str = ""
    # location_id: str = ""
    location_name: str = ""
    provider_name: str = ""
    primary_practitioner: str = ""

    def to_context_string(self) -> str:
        """
        Convert encounter data to context string for LLM.

        Returns flat list of non-empty fields in 'Label: Value' format.
        Skips fields that are None or empty string.
        """
        lines = []

        # Helper to check if field should be included
        def should_include(value) -> bool:
            return value is not None and value != ""

        # Add encounter fields
        # if should_include(self.id):
        #     lines.append(f"Encounter ID: {self.id}")
        if should_include(self.type_display):
            lines.append(f"Encounter Type: {self.type_display}")
        if should_include(self.encounter_class):
            lines.append(f"Encounter Class: {self.encounter_class}")
        if should_include(self.reason_display):
            lines.append(f"Reason: {self.reason_display}")
        if should_include(self.start_datetime):
            lines.append(f"Start Date/Time: {self.start_datetime}")
        if should_include(self.end_datetime):
            lines.append(f"End Date/Time: {self.end_datetime}")
        if should_include(self.location_name):
            lines.append(f"Location: {self.location_name}")
        if should_include(self.provider_name):
            lines.append(f"Provider: {self.provider_name}")
        if should_include(self.primary_practitioner):
            lines.append(f"Primary Practitioner: {self.primary_practitioner}")

        return "\n".join(lines)


@dataclass
class ClinicalContext:
    """Clinical context for note generation."""
    conditions: List[Dict[str, str]] = field(default_factory=list)
    procedures: List[Dict[str, str]] = field(default_factory=list)
    medications: List[Dict[str, str]] = field(default_factory=list)
    allergies: List[Dict[str, str]] = field(default_factory=list)
    immunizations: List[Dict[str, str]] = field(default_factory=list)
    observations: List[Dict[str, str]] = field(default_factory=list)
    imaging_studies: List[Dict[str, str]] = field(default_factory=list)
    devices: List[Dict[str, str]] = field(default_factory=list)

    def to_context_string(
        self,
        max_per_category: Optional[int] = None,  # Keep for backward compatibility
        max_conditions: Optional[int] = None,
        max_medications: Optional[int] = None,
        max_procedures: Optional[int] = None,
        max_allergies: Optional[int] = None,
        max_immunizations: Optional[int] = None,
        max_observations: Optional[int] = None,
        max_imaging_studies: Optional[int] = None,
        max_devices: Optional[int] = None
    ) -> str:
        """
        Convert clinical context to string for LLM.

        Args:
            max_per_category: Optional limit per category (None = no limit). Deprecated in favor of per-category limits.
            max_conditions: Optional limit for conditions (None = no limit)
            max_medications: Optional limit for medications (None = no limit)
            max_procedures: Optional limit for procedures (None = no limit)
            max_allergies: Optional limit for allergies (None = no limit)
            max_immunizations: Optional limit for immunizations (None = no limit)
            max_observations: Optional limit for observations (None = no limit)
            max_imaging_studies: Optional limit for imaging studies (None = no limit)
            max_devices: Optional limit for devices (None = no limit)

        Returns flat list with section headers for each non-empty category.
        Format:
            ## Conditions
            - Display text 1
            - Display text 2

            ## Medications
            - Display text 1
        """
        sections = []

        # Helper to format a list category
        def format_category(items: list, header: str, max_items: Optional[int]) -> Optional[str]:
            if not items:
                return None

            # Use specific limit, fall back to max_per_category, or unlimited
            limit = max_items if max_items is not None else max_per_category
            limited_items = items[:limit] if limit else items

            lines = [f"## {header}"]
            for item in limited_items:
                if isinstance(item, dict):
                    # Extract display text (adjust field names as needed)
                    display = item.get('display') or item.get('name') or item.get('description') or str(item)
                else:
                    display = str(item)
                lines.append(f"- {display}")

            return "\n".join(lines)

        # Add each category with its specific limit
        if self.conditions:
            section = format_category(self.conditions, "Conditions", max_conditions)
            if section:
                sections.append(section)

        if self.medications:
            section = format_category(self.medications, "Medications", max_medications)
            if section:
                sections.append(section)

        if self.procedures:
            section = format_category(self.procedures, "Procedures", max_procedures)
            if section:
                sections.append(section)

        if self.allergies:
            section = format_category(self.allergies, "Allergies", max_allergies)
            if section:
                sections.append(section)

        if self.immunizations:
            section = format_category(self.immunizations, "Immunizations", max_immunizations)
            if section:
                sections.append(section)

        if self.observations:
            section = format_category(self.observations, "Observations", max_observations)
            if section:
                sections.append(section)

        if self.imaging_studies:
            section = format_category(self.imaging_studies, "Imaging Studies", max_imaging_studies)
            if section:
                sections.append(section)

        if self.devices:
            section = format_category(self.devices, "Devices", max_devices)
            if section:
                sections.append(section)

        return "\n\n".join(sections)


@dataclass
class ProviderData:
    """Healthcare provider information."""
    id: str = ""
    name: str = ""
    specialty: str = ""
    organization: str = ""
    phone: str = ""
    fax: str = ""
    email: str = ""
    address: str = ""

    def to_context_string(self) -> str:
        """
        Convert provider data to context string for LLM.

        Returns flat list of non-empty fields in 'Label: Value' format.
        Skips fields that are None or empty string.
        """
        lines = []

        # Helper to check if field should be included
        def should_include(value) -> bool:
            return value is not None and value != ""

        # Add provider fields
        if should_include(self.id):
            lines.append(f"Provider ID: {self.id}")
        if should_include(self.name):
            lines.append(f"Provider Name: {self.name}")
        if should_include(self.specialty):
            lines.append(f"Specialty: {self.specialty}")
        if should_include(self.organization):
            lines.append(f"Organization: {self.organization}")
        if should_include(self.phone):
            lines.append(f"Phone: {self.phone}")
        if should_include(self.fax):
            lines.append(f"Fax: {self.fax}")
        if should_include(self.email):
            lines.append(f"Email: {self.email}")
        if should_include(self.address):
            lines.append(f"Address: {self.address}")

        return "\n".join(lines)


@dataclass
class OrganizationData:
    """Healthcare organization information."""
    id: str = ""
    name: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""


class FHIRBundleParser:
    """Parse Synthea FHIR bundles to extract patient and clinical data."""

    def __init__(self, bundle_path: Optional[Path] = None):
        self.bundle: Dict[str, Any] = {}
        self.resources_by_type: Dict[str, List[Dict]] = {}
        self.resources_by_id: Dict[str, Dict] = {}

        if bundle_path:
            self.load_bundle(bundle_path)

    def load_bundle(self, bundle_path: Path) -> None:
        """Load and index a FHIR bundle."""
        with open(bundle_path, 'r') as f:
            self.bundle = json.load(f)

        # Index resources by type and ID
        self.resources_by_type = {}
        self.resources_by_id = {}

        for entry in self.bundle.get('entry', []):
            resource = entry.get('resource', {})
            res_type = resource.get('resourceType', '')
            res_id = resource.get('id', '')
            full_url = entry.get('fullUrl', '')

            if res_type not in self.resources_by_type:
                self.resources_by_type[res_type] = []
            self.resources_by_type[res_type].append(resource)

            if res_id:
                self.resources_by_id[res_id] = resource
            if full_url:
                self.resources_by_id[full_url] = resource

    def get_resources(self, resource_type: str) -> List[Dict]:
        """Get all resources of a given type."""
        return self.resources_by_type.get(resource_type, [])

    def get_resource_by_id(self, resource_id: str) -> Optional[Dict]:
        """Get a resource by ID or full URL."""
        # Try direct lookup
        if resource_id in self.resources_by_id:
            return self.resources_by_id[resource_id]
        # Try with urn:uuid: prefix
        if resource_id.startswith('urn:uuid:'):
            return self.resources_by_id.get(resource_id)
        return self.resources_by_id.get(f'urn:uuid:{resource_id}')

    def _extract_extension_value(self, extensions: List[Dict], url: str) -> Optional[str]:
        """Extract value from a FHIR extension by URL."""
        for ext in extensions:
            if ext.get('url') == url:
                # Handle nested extensions (like us-core-race)
                if 'extension' in ext:
                    for nested in ext['extension']:
                        if 'valueCoding' in nested:
                            return nested['valueCoding'].get('display', '')
                        if 'valueString' in nested:
                            return nested['valueString']
                # Handle direct values
                if 'valueString' in ext:
                    return ext['valueString']
                if 'valueAddress' in ext:
                    addr = ext['valueAddress']
                    return f"{addr.get('city', '')}, {addr.get('state', '')}"
        return None

    def extract_patient(self) -> PatientData:
        """Extract patient demographics and identifiers."""

        """
        Extract below:
            root
            - id
            - name (nested)
            - telecom (nested)
            - gender
            - birthDate
            - deceasedDateTime
            - address (nested)
            - maritalStatus (nested)
            identifiers
            - mrn
            - 
            extensions
            - race
            - ethnicity
            - mothers maiden name
            - birth city, state and country
            - disability adjusted life years
            - quality adjusted life years
            
             
        """

        patients = self.get_resources('Patient')
        if not patients:
            return PatientData()

        patient = patients[0]
        data = PatientData()

        # Basic ID
        data.id = patient.get('id', '')

        # Extract identifiers
        data.mrn = jmespath.search("identifier[?type.coding[?code=='MR']] | [0].value", patient) or ''
        data.ssn = jmespath.search("identifier[?type.coding[?code=='SS']] | [0].value", patient) or ''
        data.drivers_license = jmespath.search("identifier[?type.coding[?code=='DL']] | [0].value", patient) or ''
        data.passport = jmespath.search("identifier[?type.coding[?code=='PPN']] | [0].value", patient) or ''

        # for identifier in patient.get('identifier', []):
        #     id_type = identifier.get('type', {}).get('coding', [{}])[0].get('code', '')
        #     id_display = identifier.get('type', {}).get('coding', [{}])[0].get('display', '')
        #     value = identifier.get('value', '')
        #
        #     if 'MR' in id_type or 'Medical Record' in id_display:
        #         data.mrn = value
        #     elif 'SS' in id_type or 'Social Security' in id_display:
        #         data.ssn = value
        #     elif 'DL' in id_type or "Driver" in id_display:
        #         data.drivers_license = value
        #     elif 'PPN' in id_type or 'Passport' in id_display:
        #         data.passport = value
        #     elif not data.mrn and id_type == '':
        #         # First unknown identifier often is MRN
        #         data.mrn = value

        # Extract name
        official_name = jmespath.search("name[?use=='official'] | [0]", patient) or {}
        data.first_name = strip_digits(' '.join(official_name.get('given', [])))
        data.last_name = strip_digits(official_name.get('family', ''))
        # data.first_name = strip_digits(jmespath.search("name[0].given | join(' ', @)", patient))
        data.last_name = strip_digits(jmespath.search("name[0].family", patient))
        # data.prefix = jmespath.search("name[0].prefix[0]", patient) or  ''
        data.full_name = f"{data.first_name} {data.last_name}".strip()
        data.nicknames = jmespath.search("(name[?use=='usual'] | [0].given || `[]`) | join(' ', @)", patient) or ""

        # Demographics
        data.gender = patient.get('gender', '')
        data.birth_date = patient.get('birthDate', '')
        data.deceased_date = patient.get('deceasedDateTime')

        # Calculate age
        if data.birth_date:
            try:
                birth = date.fromisoformat(data.birth_date)
                ref_date = date.today()
                if data.deceased_date:
                    ref_date = date.fromisoformat(data.deceased_date[:10])
                data.age = ref_date.year - birth.year - (
                    (ref_date.month, ref_date.day) < (birth.month, birth.day)
                )
            except ValueError:
                data.age = 0

        # Extract emergency contact information (if any)
        if patient.get('contact'):
            emergency_contact = jmespath.search("[?relationship[?coding[?contains(['CP', 'EP', 'N'], code)]]] | [0]", patient["contact"])
            if emergency_contact:
                emergency_contact_name = emergency_contact.get('name', {})
                emergency_contact_first_name = strip_digits(' '.join(emergency_contact_name.get('given', [])))
                emergency_contact_last_name = strip_digits(emergency_contact_name.get('family', ''))
                data.emergency_contact_name = f"{emergency_contact_first_name} {emergency_contact_last_name}".strip()
                data.emergency_contact_phone = jmespath.search("telecom[?system=='phone'] | [0].value", emergency_contact) or ''

        # Extract address
        address_data = patient.get('address', [{}])[0]
        data.address_line = address_data.get('line', [""])[0]
        data.city = address_data.get('city', '')
        data.state = address_data.get('state', '')
        data.country = address_data.get('country', '')
        data.zip_code = address_data.get('postalCode', '')
        # print([data.city, data.state])
        data.address_city_and_state = ", ".join([address_part for address_part in [data.city, data.state] if address_part]).strip()
        # print(f"Address City & State {data.address_city_and_state}")
        data.address_state_and_country = ", ".join([address_part for address_part in [data.state, data.country] if address_part]).strip()
        data.address_city_state_and_country = ", ".join([address_part for address_part in [data.city, data.state, data.country] if address_part]).strip()
        data.full_address = ", ".join([address_part for address_part in [data.address_line, data.city, data.state, data.zip_code] if address_part]).strip()

        data.phone = jmespath.search(f"telecom[?system=='phone'] | [0].value", patient) or ''

        # Extract extensions
        data.race = jmespath.search(f"extension[?url=='{ExtensionURL.US_CORE_RACE}'] | [0].extension[1].valueString", patient) or ''
        data.ethnicity = jmespath.search(f"extension[?url=='{ExtensionURL.US_CORE_ETHNICITY}'] | [0].extension[1].valueString", patient) or ''
        data.mothers_maiden_name = strip_digits(jmespath.search(f"extension[?url=='{ExtensionURL.MOTHERS_MAIDEN_NAME}'] | [0].valueString", patient))
        birth_place = jmespath.search(f"extension[?url=='{ExtensionURL.BIRTH_PLACE}'] | [0].valueAddress", patient) or {}
        data.birth_city = birth_place.get('city', '')
        data.birth_state = birth_place.get('state', '')
        data.birth_country = birth_place.get('country', '')
        data.birth_city_and_state = ", ".join([address_part for address_part in [data.birth_city, data.birth_state] if address_part]).strip()
        data.birth_state_and_country = ", ".join([address_part for address_part in [data.birth_state, data.birth_country] if address_part]).strip()
        data.birth_city_state_and_country = ", ".join([address_part for address_part in [data.city, data.state, data.country] if address_part]).strip()
        data.disability_adjusted_life_years = round_and_to_str(jmespath.search(f"extension[?url=='{ExtensionURL.DISABILITY_ADJUSTED_LIFE_YEARS}'] | [0].valueDecimal", patient))
        data.quality_adjusted_life_years = round_and_to_str(jmespath.search(f"extension[?url=='{ExtensionURL.QUALITY_ADJUSTED_LIFE_YEARS}'] | [0].valueDecimal", patient))

        # Marital status
        data.marital_status = MaritalStatus.from_code(jmespath.search('maritalStatus.coding[0].code', patient))

        return data

    def extract_encounters(self) -> List[EncounterData]:
        """Extract all encounters from the bundle."""
        encounters = []
        for enc in self.get_resources('Encounter'):
            data = EncounterData()
            data.id = enc.get('id', '')

            # Type
            # data.type_display = jmespath.search('')
            enc_type = enc.get('type', [{}])[0].get('coding', [{}])[0]
            # data.type_code = enc_type.get('code', '')
            # print('DEBUGGG', enc)
            # print('DEBUGGG2222')
            # print(jmespath.search("type[].coding[].display", enc))
            # print("ID:", data.id)
            types = jmespath.search("type[].coding[].display", enc)
            data.type_display = ', '.join(types) if types else ''

            # data.type_display = jmespath.search("type[].{val: coding[0].display || text}.val | [?@ ] | join(', ', @)", enc)
            # data.type_display = enc_type.get('display', '')

            # Class
            data.encounter_class = enc.get('class', {}).get('code', '')

            # Reason
            reasons = jmespath.search("reasonCode[].coding[].display", enc)
            data.reason_display = ', '.join(reasons) if reasons else ''
            # data.reason_display = jmespath.search("reasonCode[].coding[].display | join(', ', @)", enc)
            # if enc.get('reasonCode'):
            #     reason = enc['reasonCode'][0].get('coding', [{}])[0]
            #     data.reason_code = reason.get('code', '')
            #     data.reason_display = reason.get('display', '')

            # Period
            period = enc.get('period', {})
            data.start_datetime = human_readable_datetime(period.get('start', ''))
            data.end_datetime = human_readable_datetime(period.get('end', ''))

            # Extract location and providers
            locations = jmespath.search("location[].location.display", enc) or []
            data.location_name = ', '.join(locations)
            data.provider_name = jmespath.search("serviceProvider.display", enc) or []

            # Extract primary practitioner
            primary_practitioner = jmespath.search("participant[?type[?coding[?code=='PPRF']]].individual | [0]", enc) or {}
            data.primary_practitioner = strip_digits(primary_practitioner.get('display', ''))

            encounters.append(data)

        return encounters

    def extract_clinical_context(self, encounter_id: Optional[str] = None) -> ClinicalContext:
        """Extract clinical context, optionally filtered by encounter."""
        context = ClinicalContext()

        # Helper to check if resource belongs to encounter
        def matches_encounter(resource: Dict) -> bool:
            if not encounter_id:
                return True
            enc_ref = resource.get('encounter', {}).get('reference', '')
            return encounter_id in enc_ref

        # Conditions
        for cond in self.get_resources('Condition'):
            if matches_encounter(cond):
                coding = cond.get('code', {}).get('coding', [{}])[0]
                context.conditions.append({
                    'code': coding.get('code', ''),
                    'display': coding.get('display', ''),
                    'onset': cond.get('onsetDateTime', '')
                })

        # Procedures
        for proc in self.get_resources('Procedure'):
            if matches_encounter(proc):
                coding = proc.get('code', {}).get('coding', [{}])[0]
                context.procedures.append({
                    'code': coding.get('code', ''),
                    'display': coding.get('display', ''),
                    'date': proc.get('performedDateTime', proc.get('performedPeriod', {}).get('start', ''))
                })

        # Medications
        for med in self.get_resources('MedicationRequest'):
            if matches_encounter(med):
                med_name = ''
                if 'medicationCodeableConcept' in med:
                    med_name = med['medicationCodeableConcept'].get('coding', [{}])[0].get('display', '')
                elif 'medicationReference' in med:
                    ref = med['medicationReference'].get('reference', '')
                    med_resource = self.get_resource_by_id(ref)
                    if med_resource:
                        med_name = med_resource.get('code', {}).get('coding', [{}])[0].get('display', '')
                context.medications.append({
                    'name': med_name,
                    'status': med.get('status', '')
                })

        # Immunizations
        for imm in self.get_resources('Immunization'):
            if matches_encounter(imm):
                coding = imm.get('vaccineCode', {}).get('coding', [{}])[0]
                context.immunizations.append({
                    'code': coding.get('code', ''),
                    'display': coding.get('display', ''),
                    'date': imm.get('occurrenceDateTime', '')
                })

        # Imaging Studies
        for img in self.get_resources('ImagingStudy'):
            if matches_encounter(img):
                modality = img.get('modality', [{}])[0] if img.get('modality') else {}
                context.imaging_studies.append({
                    'modality': modality.get('display', modality.get('code', '')),
                    'description': img.get('description', ''),
                    'date': img.get('started', '')
                })

        # Devices
        for dev in self.get_resources('Device'):
            udi = dev.get('udiCarrier', [{}])[0] if dev.get('udiCarrier') else {}
            context.devices.append({
                'type': dev.get('type', {}).get('coding', [{}])[0].get('display', ''),
                'udi': udi.get('deviceIdentifier', ''),
                'manufacturer': dev.get('manufacturer', '')
            })

        return context

    def extract_providers(self) -> List[ProviderData]:
        """Extract provider information."""
        providers = []
        for prac in self.get_resources('Practitioner'):
            data = ProviderData()
            data.id = prac.get('id', '')

            if prac.get('name'):
                name = prac['name'][0]
                given = ' '.join(name.get('given', []))
                family = name.get('family', '')
                prefix = ' '.join(name.get('prefix', []))
                data.name = f"{prefix} {given} {family}".strip()

            providers.append(data)

        return providers

    def extract_organizations(self) -> List[OrganizationData]:
        """Extract organization information."""
        organizations = []
        for org in self.get_resources('Organization'):
            data = OrganizationData()
            data.id = org.get('id', '')
            data.name = org.get('name', '')

            for telecom in org.get('telecom', []):
                if telecom.get('system') == 'phone':
                    data.phone = telecom.get('value', '')
                    break

            if org.get('address'):
                addr = org['address'][0]
                data.address = ', '.join(addr.get('line', []))
                data.city = addr.get('city', '')
                data.state = addr.get('state', '')
                data.zip_code = addr.get('postalCode', '')

            organizations.append(data)

        return organizations

    def get_document_references(self) -> List[Dict]:
        """Get existing DocumentReference resources (clinical notes)."""
        return self.get_resources('DocumentReference')

    def get_full_context(self) -> Dict[str, Any]:
        """Extract all context needed for note generation."""
        patient = self.extract_patient()
        encounters = self.extract_encounters()
        clinical = self.extract_clinical_context()
        providers = self.extract_providers()
        organizations = self.extract_organizations()

        return {
            'patient': patient.to_dict(),
            'encounters': [vars(e) for e in encounters],
            'clinical': {
                'conditions': clinical.conditions,
                'procedures': clinical.procedures,
                'medications': clinical.medications,
                'immunizations': clinical.immunizations,
                'imaging_studies': clinical.imaging_studies,
                'devices': clinical.devices,
            },
            'providers': [vars(p) for p in providers],
            'organizations': [vars(o) for o in organizations],
        }
