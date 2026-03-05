"""FHIR data models for synthetic patient data generation and note context extraction."""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from enum import StrEnum

from ..utils import should_include_in_llm_context

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

        # Core identifiers
        if should_include_in_llm_context(self.id):
            lines.append(f"Patient ID: {self.id}")
        if should_include_in_llm_context(self.mrn):
            lines.append(f"MRN: {self.mrn}")
        if should_include_in_llm_context(self.ssn):
            lines.append(f"SSN: {self.ssn}")
        if should_include_in_llm_context(self.drivers_license):
            lines.append(f"Driver's License: {self.drivers_license}")
        if should_include_in_llm_context(self.passport):
            lines.append(f"Passport: {self.passport}")

        # Demographics - Names
        if should_include_in_llm_context(self.first_name):
            lines.append(f"First Name: {self.first_name}")
        if should_include_in_llm_context(self.nicknames):
            lines.append(f"Nicknames: {self.nicknames}")
        if should_include_in_llm_context(self.last_name):
            lines.append(f"Last Name: {self.last_name}")
        if should_include_in_llm_context(self.full_name):
            lines.append(f"Full Name: {self.full_name}")
        if should_include_in_llm_context(self.prefix):
            lines.append(f"Prefix: {self.prefix}")

        # Demographics - Basic info
        if should_include_in_llm_context(self.gender):
            lines.append(f"Gender: {self.gender}")
        if should_include_in_llm_context(self.birth_date):
            lines.append(f"Date of Birth: {self.birth_date}")
        if should_include_in_llm_context(self.age, allow_zero_if_number_field=True):
            lines.append(f"Age: {self.age} years old")
        if should_include_in_llm_context(self.deceased_date):
            lines.append(f"Deceased Date: {self.deceased_date}")

        # Contact info
        if should_include_in_llm_context(self.phone):
            lines.append(f"Phone: {self.phone}")
        if should_include_in_llm_context(self.email):
            lines.append(f"Email: {self.email}")
        if should_include_in_llm_context(self.fax):
            lines.append(f"Fax: {self.fax}")
        if should_include_in_llm_context(self.address_line):
            lines.append(f"Address Line: {self.address_line}")
        if should_include_in_llm_context(self.city):
            lines.append(f"City: {self.city}")
        if should_include_in_llm_context(self.state):
            lines.append(f"State: {self.state}")
        if should_include_in_llm_context(self.zip_code):
            lines.append(f"Zip Code: {self.zip_code}")
        if should_include_in_llm_context(self.country):
            lines.append(f"Country: {self.country}")
        if should_include_in_llm_context(self.full_address):
            lines.append(f"Full Address: {self.full_address}")

        # Additional demographics
        if should_include_in_llm_context(self.race):
            lines.append(f"Race: {self.race}")
        if should_include_in_llm_context(self.ethnicity):
            lines.append(f"Ethnicity: {self.ethnicity}")
        if should_include_in_llm_context(self.marital_status):
            lines.append(f"Marital Status: {self.marital_status}")
        if should_include_in_llm_context(self.birth_city):
            lines.append(f"Birth City: {self.birth_city}")
        if should_include_in_llm_context(self.birth_state):
            lines.append(f"Birth State: {self.birth_state}")
        if should_include_in_llm_context(self.birth_country):
            lines.append(f"Birth Country: {self.birth_country}")
        if should_include_in_llm_context(self.mothers_maiden_name):
            lines.append(f"Mother's Maiden Name: {self.mothers_maiden_name}")

        # Additional information
        if should_include_in_llm_context(self.disability_adjusted_life_years):
            lines.append(f"Disability Adjusted Life Years: {self.disability_adjusted_life_years}")
        if should_include_in_llm_context(self.quality_adjusted_life_years):
            lines.append(f"Quality Adjusted Life Years: {self.quality_adjusted_life_years}")
        if should_include_in_llm_context(self.health_plan_id):
            lines.append(f"Health Plan ID: {self.health_plan_id}")
        if should_include_in_llm_context(self.account_number):
            lines.append(f"Account Number: {self.account_number}")
        if should_include_in_llm_context(self.vehicle_id):
            lines.append(f"Vehicle ID: {self.vehicle_id}")
        if should_include_in_llm_context(self.license_plate):
            lines.append(f"License Plate: {self.license_plate}")
        if should_include_in_llm_context(self.ip_address):
            lines.append(f"IP Address: {self.ip_address}")
        if should_include_in_llm_context(self.patient_portal_url):
            lines.append(f"Patient Portal URL: {self.patient_portal_url}")

        # Emergency contact
        if should_include_in_llm_context(self.emergency_contact_name):
            lines.append(f"Emergency Contact Name: {self.emergency_contact_name}")
        if should_include_in_llm_context(self.emergency_contact_phone):
            lines.append(f"Emergency Contact Phone: {self.emergency_contact_phone}")
        if should_include_in_llm_context(self.emergency_contact_relationship):
            lines.append(f"Emergency Contact Relationship: {self.emergency_contact_relationship}")

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

        # Add encounter fields
        if should_include_in_llm_context(self.type_display):
            lines.append(f"Encounter Type: {self.type_display}")
        if should_include_in_llm_context(self.encounter_class):
            lines.append(f"Encounter Class: {self.encounter_class}")
        if should_include_in_llm_context(self.reason_display):
            lines.append(f"Reason: {self.reason_display}")
        if should_include_in_llm_context(self.start_datetime):
            lines.append(f"Start Date/Time: {self.start_datetime}")
        if should_include_in_llm_context(self.end_datetime):
            lines.append(f"End Date/Time: {self.end_datetime}")
        if should_include_in_llm_context(self.location_name):
            lines.append(f"Location: {self.location_name}")
        if should_include_in_llm_context(self.provider_name):
            lines.append(f"Provider: {self.provider_name}")
        if should_include_in_llm_context(self.primary_practitioner):
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

        # Add provider fields
        if should_include_in_llm_context(self.id):
            lines.append(f"Provider ID: {self.id}")
        if should_include_in_llm_context(self.name):
            lines.append(f"Provider Name: {self.name}")
        if should_include_in_llm_context(self.specialty):
            lines.append(f"Specialty: {self.specialty}")
        if should_include_in_llm_context(self.organization):
            lines.append(f"Organization: {self.organization}")
        if should_include_in_llm_context(self.phone):
            lines.append(f"Phone: {self.phone}")
        if should_include_in_llm_context(self.fax):
            lines.append(f"Fax: {self.fax}")
        if should_include_in_llm_context(self.email):
            lines.append(f"Email: {self.email}")
        if should_include_in_llm_context(self.address):
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
