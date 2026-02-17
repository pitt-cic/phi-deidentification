"""FHIR Bundle parser for extracting patient data and clinical context."""
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import jmespath

from .models.fhir_models import (
    ClinicalContext,
    EncounterData,
    ExtensionURL,
    MaritalStatus,
    OrganizationData,
    PatientData,
    ProviderData,
)
from .utils import human_readable_datetime, round_and_to_str, strip_digits


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

        data.phone = jmespath.search("telecom[?system=='phone'] | [0].value", patient) or ''

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
            # enc_type = enc.get('type', [{}])[0].get('coding', [{}])[0]
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
