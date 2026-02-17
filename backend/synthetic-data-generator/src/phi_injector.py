"""PHI Injector - Adds PHI types not present in Synthea data."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .phi_generator import PHIGenerator


@dataclass
class InjectedPHI:
    """PHI values injected to supplement Synthea data."""
    # Contact info not in Synthea
    email: str = ""
    fax: str = ""

    # Identifiers not in Synthea
    health_plan_id: str = ""
    account_number: str = ""
    vehicle_id: str = ""
    license_plate: str = ""

    # Technical identifiers
    ip_address: str = ""
    patient_portal_url: str = ""

    # Emergency contact (often not in FHIR)
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""
    emergency_contact_relationship: str = ""

    # Provider contact info
    provider_fax: str = ""
    provider_email: str = ""

    # Facility info
    facility_name: str = ""
    facility_phone: str = ""
    facility_fax: str = ""

    # Device IDs (supplement if not in bundle)
    device_id: str = ""
    scanner_id: str = ""

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "fax": self.fax,
            "health_plan_id": self.health_plan_id,
            "account_number": self.account_number,
            "vehicle_id": self.vehicle_id,
            "license_plate": self.license_plate,
            "ip_address": self.ip_address,
            "patient_portal_url": self.patient_portal_url,
            "emergency_contact_name": self.emergency_contact_name,
            "emergency_contact_phone": self.emergency_contact_phone,
            "emergency_contact_relationship": self.emergency_contact_relationship,
            "provider_fax": self.provider_fax,
            "provider_email": self.provider_email,
            "facility_name": self.facility_name,
            "facility_phone": self.facility_phone,
            "facility_fax": self.facility_fax,
            "device_id": self.device_id,
            "scanner_id": self.scanner_id,
        }


class PHIInjector:
    """
    Inject additional PHI values that are not present in Synthea FHIR bundles.

    Synthea generates many PHI types but lacks:
    - Email addresses
    - Fax numbers
    - Health plan IDs
    - Account numbers
    - Vehicle identifiers
    - IP addresses
    - URLs
    - Emergency contact details
    """

    def __init__(self, phi_generator: Optional[PHIGenerator] = None, seed: Optional[int] = None):
        self.phi_gen = phi_generator or PHIGenerator(seed=seed)

    def inject(self, synthea_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inject additional PHI into Synthea context.

        Args:
            synthea_context: Context extracted from FHIR bundle (from FHIRBundleParser.get_full_context())

        Returns:
            Enhanced context with injected PHI
        """
        # Generate injected PHI
        injected = InjectedPHI()

        # Generate contact info
        email_domain = self.phi_gen.generate_email_domain()
        if (
                synthea_context.get('patient', {}).get('first_name') and
                synthea_context.get('patient', {}).get('last_name')
        ):

            injected.email = f"{synthea_context['patient']['first_name'].lower()}.{synthea_context['patient']['last_name'].lower()}@{email_domain}"
        elif synthea_context.get('patient', {}).get('first_name'):
            injected.email = f"{synthea_context['patient']['first_name'].lower()}@{email_domain}"
        elif synthea_context.get('patient', {}).get('last_name'):
            injected.email = f"{synthea_context['patient']['last_name'].lower()}@{email_domain}"
        else:
            injected.email = self.phi_gen.generate_email()


        injected.fax = self.phi_gen.generate_fax()

        # Generate identifiers
        injected.health_plan_id = self.phi_gen.generate_health_plan_id()
        injected.account_number = self.phi_gen.generate_account_number()
        injected.vehicle_id = self.phi_gen.generate_vehicle_id()
        injected.license_plate = self.phi_gen.generate_license_plate()

        # Generate technical identifiers
        injected.ip_address = self.phi_gen.generate_ip_address()
        # injected.patient_portal_url = self.phi_gen.generate_patient_portal_url()

        # Generate emergency contact
        # injected.emergency_contact_name = self.phi_gen.generate_name()["full_name"]
        # injected.emergency_contact_phone = self.phi_gen.generate_phone()
        # injected.emergency_contact_relationship = self.phi_gen.fake.random_element([
        #     "spouse", "parent", "child", "sibling", "friend", "partner"
        # ])

        # Generate provider contact info
        # injected.provider_fax = self.phi_gen.generate_fax()
        # injected.provider_email = self.phi_gen.generate_email()

        # Generate facility info (if not in bundle)
        current_encounter = synthea_context.get('current_encounter', {})
        if not (current_encounter.get('location_name', '') or current_encounter.get('provider_name', '')):
            injected.facility_name = self.phi_gen.generate_hospital_name()
            injected.facility_phone = self.phi_gen.generate_phone()
            injected.facility_fax = self.phi_gen.generate_fax()
        else:
            # org = synthea_context['organizations'][0]
            injected.facility_name = current_encounter.get('provider_name', current_encounter.get('location_name', ''))
            injected.facility_phone = self.phi_gen.generate_phone()
            injected.facility_fax = self.phi_gen.generate_fax()

        # Generate device IDs (supplement if not in bundle)
        # injected.device_id = self.phi_gen.generate_device_id()
        # injected.scanner_id = f"SCN-{self.phi_gen.fake.random_int(10000, 99999)}"

        # Merge injected PHI into context
        enhanced_context = synthea_context.copy()
        enhanced_context['injected'] = injected.to_dict()

        # Also flatten key fields into patient for easier template access
        if 'patient' in enhanced_context:
            patient = enhanced_context['patient']
            patient['email'] = injected.email
            patient['fax'] = injected.fax
            patient['health_plan_id'] = injected.health_plan_id
            patient['account_number'] = injected.account_number
            patient['vehicle_id'] = injected.vehicle_id
            patient['license_plate'] = injected.license_plate
            patient['ip_address'] = injected.ip_address
            patient['patient_portal_url'] = injected.patient_portal_url
            patient['emergency_contact_name'] = injected.emergency_contact_name
            patient['emergency_contact_phone'] = injected.emergency_contact_phone
            patient['emergency_contact_relationship'] = injected.emergency_contact_relationship

        # Add provider contact info
        # if enhanced_context.get('providers'):
        #     for provider in enhanced_context['providers']:
        #         provider['fax'] = injected.provider_fax
        #         provider['email'] = injected.provider_email
        # else:
        #     # Create a synthetic provider if none exists
        #     enhanced_context['providers'] = [{
        #         'id': '',
        #         'name': self.phi_gen.generate_provider_name(),
        #         'specialty': 'Internal Medicine',
        #         'organization': injected.facility_name,
        #         'phone': self.phi_gen.generate_phone(),
        #         'fax': injected.provider_fax,
        #         'email': injected.provider_email,
        #         'address': ''
        #     }]

        # Ensure facility info is available
        enhanced_context['facility'] = {
            'name': injected.facility_name,
            'phone': injected.facility_phone,
            'fax': injected.facility_fax,
        }

        # Add device info
        # enhanced_context['device'] = {
        #     'id': injected.device_id,
        #     'scanner_id': injected.scanner_id,
        # }

        return enhanced_context

    def get_phi_mapping(self) -> Dict[str, str]:
        """
        Get mapping of PHI types to their placeholder names.

        Returns:
            Dict mapping PHI field names to placeholder format
        """
        return {
            # From Synthea
            "full_name": "{{NAME}}",
            "first_name": "{{FIRST_NAME}}",
            "last_name": "{{LAST_NAME}}",
            "birth_date": "{{DOB}}",
            "age": "{{AGE}}",
            "gender": "{{GENDER}}",
            "ssn": "{{SSN}}",
            "mrn": "{{MRN}}",
            "drivers_license": "{{DRIVERS_LICENSE}}",
            "passport": "{{PASSPORT}}",
            "phone": "{{PHONE}}",
            "address_line": "{{ADDRESS}}",
            "city": "{{CITY}}",
            "state": "{{STATE}}",
            "zip_code": "{{ZIP}}",
            "full_address": "{{FULL_ADDRESS}}",

            # Injected
            "email": "{{EMAIL}}",
            "fax": "{{FAX}}",
            "health_plan_id": "{{HEALTH_PLAN_ID}}",
            "account_number": "{{ACCOUNT_NUMBER}}",
            "vehicle_id": "{{VEHICLE_ID}}",
            "license_plate": "{{LICENSE_PLATE}}",
            "ip_address": "{{IP_ADDRESS}}",
            "patient_portal_url": "{{URL}}",
            "emergency_contact_name": "{{EMERGENCY_CONTACT_NAME}}",
            "emergency_contact_phone": "{{EMERGENCY_CONTACT_PHONE}}",
            "device_id": "{{DEVICE_ID}}",

            # Provider
            "provider_name": "{{PROVIDER_NAME}}",
            "provider_phone": "{{PROVIDER_PHONE}}",
            "provider_fax": "{{PROVIDER_FAX}}",

            # Facility
            "facility_name": "{{FACILITY_NAME}}",
            "facility_phone": "{{FACILITY_PHONE}}",
            "facility_fax": "{{FACILITY_FAX}}",

            # Dates
            "encounter_date": "{{ENCOUNTER_DATE}}",
            "encounter_datetime": "{{ENCOUNTER_DATETIME}}",
        }
