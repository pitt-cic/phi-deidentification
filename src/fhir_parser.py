"""FHIR Bundle parser for extracting patient data and clinical context."""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    last_name: str = ""
    full_name: str = ""
    prefix: str = ""
    gender: str = ""
    birth_date: str = ""
    age: int = 0
    deceased_date: Optional[str] = None

    # Contact info
    phone: str = ""
    address_line: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    country: str = ""
    full_address: str = ""

    # Additional demographics
    race: str = ""
    ethnicity: str = ""
    marital_status: str = ""
    birth_place: str = ""
    mothers_maiden_name: str = ""

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
            "birth_place": self.birth_place,
            "mothers_maiden_name": self.mothers_maiden_name,
        }


@dataclass
class EncounterData:
    """Extracted encounter information."""
    id: str = ""
    type_code: str = ""
    type_display: str = ""
    encounter_class: str = ""
    reason_code: str = ""
    reason_display: str = ""
    start_datetime: str = ""
    end_datetime: str = ""
    provider_id: str = ""
    location_id: str = ""


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


@dataclass
class ProviderData:
    """Healthcare provider information."""
    id: str = ""
    name: str = ""
    specialty: str = ""
    organization: str = ""
    phone: str = ""
    address: str = ""


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

    # US Core extension URLs
    US_CORE_RACE = 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-race'
    US_CORE_ETHNICITY = 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity'
    MOTHERS_MAIDEN_NAME = 'http://hl7.org/fhir/StructureDefinition/patient-mothersMaidenName'
    BIRTH_PLACE = 'http://hl7.org/fhir/StructureDefinition/patient-birthPlace'

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
        patients = self.get_resources('Patient')
        if not patients:
            return PatientData()

        patient = patients[0]
        data = PatientData()

        # Basic ID
        data.id = patient.get('id', '')

        # Extract identifiers
        for identifier in patient.get('identifier', []):
            id_type = identifier.get('type', {}).get('coding', [{}])[0].get('code', '')
            id_display = identifier.get('type', {}).get('coding', [{}])[0].get('display', '')
            value = identifier.get('value', '')

            if 'MR' in id_type or 'Medical Record' in id_display:
                data.mrn = value
            elif 'SS' in id_type or 'Social Security' in id_display:
                data.ssn = value
            elif 'DL' in id_type or "Driver" in id_display:
                data.drivers_license = value
            elif 'PPN' in id_type or 'Passport' in id_display:
                data.passport = value
            elif not data.mrn and id_type == '':
                # First unknown identifier often is MRN
                data.mrn = value

        # Extract name
        if patient.get('name'):
            name = patient['name'][0]
            data.first_name = ' '.join(name.get('given', []))
            data.last_name = name.get('family', '')
            data.prefix = ' '.join(name.get('prefix', []))
            data.full_name = f"{data.first_name} {data.last_name}".strip()

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

        # Extract address
        if patient.get('address'):
            addr = patient['address'][0]
            data.address_line = ', '.join(addr.get('line', []))
            data.city = addr.get('city', '')
            data.state = addr.get('state', '')
            data.zip_code = addr.get('postalCode', '')
            data.country = addr.get('country', 'US')
            data.full_address = f"{data.address_line}, {data.city}, {data.state} {data.zip_code}".strip(', ')

        # Extract telecom (phone)
        for telecom in patient.get('telecom', []):
            if telecom.get('system') == 'phone':
                data.phone = telecom.get('value', '')
                break

        # Extract extensions
        extensions = patient.get('extension', [])
        data.race = self._extract_extension_value(extensions, self.US_CORE_RACE) or ''
        data.ethnicity = self._extract_extension_value(extensions, self.US_CORE_ETHNICITY) or ''
        data.mothers_maiden_name = self._extract_extension_value(extensions, self.MOTHERS_MAIDEN_NAME) or ''
        data.birth_place = self._extract_extension_value(extensions, self.BIRTH_PLACE) or ''

        # Marital status
        marital = patient.get('maritalStatus', {}).get('coding', [{}])[0]
        data.marital_status = marital.get('display', '')

        return data

    def extract_encounters(self) -> List[EncounterData]:
        """Extract all encounters from the bundle."""
        encounters = []
        for enc in self.get_resources('Encounter'):
            data = EncounterData()
            data.id = enc.get('id', '')

            # Type
            enc_type = enc.get('type', [{}])[0].get('coding', [{}])[0]
            data.type_code = enc_type.get('code', '')
            data.type_display = enc_type.get('display', '')

            # Class
            data.encounter_class = enc.get('class', {}).get('code', '')

            # Reason
            if enc.get('reasonCode'):
                reason = enc['reasonCode'][0].get('coding', [{}])[0]
                data.reason_code = reason.get('code', '')
                data.reason_display = reason.get('display', '')

            # Period
            period = enc.get('period', {})
            data.start_datetime = period.get('start', '')
            data.end_datetime = period.get('end', '')

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
