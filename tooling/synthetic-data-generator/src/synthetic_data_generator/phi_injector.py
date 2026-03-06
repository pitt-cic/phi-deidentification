"""PHI Injector - Adds PHI types not present in Synthea data."""
from typing import Any, Dict, Optional

from .models.note_models import InjectedPHI
from .phi_generator import PHIGenerator


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

        # Generate facility info (if not in bundle)
        current_encounter = synthea_context.get('current_encounter', {})
        if not (current_encounter.get('location_name', '') or current_encounter.get('provider_name', '')):
            injected.facility_name = self.phi_gen.generate_hospital_name()
            injected.facility_phone = self.phi_gen.generate_phone()
            injected.facility_fax = self.phi_gen.generate_fax()
        else:
            injected.facility_name = current_encounter.get('provider_name', current_encounter.get('location_name', ''))
            injected.facility_phone = self.phi_gen.generate_phone()
            injected.facility_fax = self.phi_gen.generate_fax()

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

        # Ensure facility info is available
        enhanced_context['facility'] = {
            'name': injected.facility_name,
            'phone': injected.facility_phone,
            'fax': injected.facility_fax,
        }

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
