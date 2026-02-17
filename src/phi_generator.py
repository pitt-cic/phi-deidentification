"""PHI value generator using Faker library."""

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from faker import Faker

from .config import PHIType


@dataclass
class PHIValue:
    """A generated PHI value with its type."""
    phi_type: PHIType
    value: str

    def to_dict(self) -> dict:
        return {
            "type": self.phi_type.value,
            "value": self.value
        }


class PHIGenerator:
    """Generate realistic PHI values using Faker."""

    def __init__(self, seed: Optional[int] = None):
        self.fake = Faker('en_US')
        if seed is not None:
            Faker.seed(seed)
            random.seed(seed)

    def generate_name(self) -> str:
        """Generate a full name."""
        return self.fake.name()

    def generate_first_name(self) -> str:
        """Generate a first name."""
        return self.fake.first_name()

    def generate_last_name(self) -> str:
        """Generate a last name."""
        return self.fake.last_name()

    def generate_address(self) -> str:
        """Generate a full street address."""
        return self.fake.address().replace('\n', ', ')

    def generate_street_address(self) -> str:
        """Generate just the street address."""
        return self.fake.street_address()

    def generate_city(self) -> str:
        """Generate a city name."""
        return self.fake.city()

    def generate_state(self) -> str:
        """Generate a state abbreviation."""
        return self.fake.state_abbr()

    def generate_zip(self) -> str:
        """Generate a ZIP code."""
        return self.fake.zipcode()
    
    # TODO: add different date formats randomly
    def generate_date(self, start_year: int = 1950, end_year: int = 2024) -> str:
        """Generate a date in MM/DD/YYYY format."""
        start_date = date(start_year, 1, 1)
        end_date = date(end_year, 12, 31)
        random_date = self.fake.date_between(start_date=start_date, end_date=end_date)
        return random_date.strftime("%m/%d/%Y")

    # TODO: add different date formats randomly
    def generate_dob(self, min_age: int = 18, max_age: int = 90) -> str:
        """Generate a date of birth for a person of given age range."""
        today = date.today()
        start_date = today - timedelta(days=max_age * 365)
        end_date = today - timedelta(days=min_age * 365)
        dob = self.fake.date_between(start_date=start_date, end_date=end_date)
        return dob.strftime("%m/%d/%Y")

    def generate_datetime(self) -> str:
        """Generate a datetime string."""
        dt = self.fake.date_time_this_year()
        return dt.strftime("%m/%d/%Y %H:%M")
    
    # TODO: add different phone number formats randomly
    def generate_phone(self) -> str:
        """Generate a phone number."""
        return self.fake.phone_number()

    def generate_simple_phone(self) -> str:
        """Generate a simple phone number format."""
        return f"{self.fake.random_int(200, 999)}-{self.fake.random_int(100, 999)}-{self.fake.random_int(1000, 9999)}"

    def generate_fax(self) -> str:
        """Generate a fax number."""
        return f"{self.fake.random_int(200, 999)}-{self.fake.random_int(100, 999)}-{self.fake.random_int(1000, 9999)}"

    def generate_email(self) -> str:
        """Generate an email address."""
        return self.fake.email()

    def generate_ssn(self) -> str:
        """Generate a Social Security Number."""
        return self.fake.ssn()

    def generate_mrn(self) -> str:
        """Generate a Medical Record Number."""
        return f"MRN-{self.fake.random_int(100000, 999999)}"

    def generate_health_plan_id(self) -> str:
        """Generate a health plan beneficiary ID."""
        prefix = random.choice(["BCBS", "UHC", "AETNA", "CIGNA", "HUM"])
        return f"{prefix}-{self.fake.random_int(100000000, 999999999)}"

    def generate_account_number(self) -> str:
        """Generate an account number."""
        return f"ACCT-{self.fake.random_int(10000000, 99999999)}"

    def generate_drivers_license(self) -> str:
        """Generate a driver's license number."""
        state = self.fake.state_abbr()
        number = self.fake.random_int(10000000, 99999999)
        return f"{state}-{number}"

    def generate_vehicle_id(self) -> str:
        """Generate a vehicle identification number (VIN)."""
        # Simplified VIN-like format
        chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
        return ''.join(random.choice(chars) for _ in range(17))

    def generate_license_plate(self) -> str:
        """Generate a license plate number."""
        return self.fake.license_plate()

    def generate_device_id(self) -> str:
        """Generate a medical device ID (UDI-like)."""
        return f"(01){self.fake.random_int(10000000000000, 99999999999999)}(17){self.fake.random_int(100000, 999999)}"

    def generate_url(self) -> str:
        """Generate a URL."""
        return self.fake.url()

    def generate_patient_portal_url(self) -> str:
        """Generate a patient portal URL."""
        hospital = self.fake.company().replace(' ', '').replace(',', '').lower()
        return f"https://portal.{hospital}.org/patient"

    def generate_ip_address(self) -> str:
        """Generate an IP address."""
        return self.fake.ipv4()

    def generate_provider_name(self) -> str:
        """Generate a healthcare provider name with title."""
        titles = ["Dr.", "Dr.", "Dr.", "NP", "PA"]  # Weighted towards Dr.
        title = random.choice(titles)
        return f"{title} {self.fake.name()}"

    def generate_hospital_name(self) -> str:
        """Generate a hospital name."""
        suffixes = ["Medical Center", "Hospital", "Health System", "Regional Medical Center"]
        city = self.fake.city()
        suffix = random.choice(suffixes)
        return f"{city} {suffix}"

    def generate_all_for_note(self, phi_types: List[PHIType]) -> Dict[PHIType, PHIValue]:
        """
        Generate PHI values for all specified types.

        Args:
            phi_types: List of PHI types to generate

        Returns:
            Dictionary mapping PHI type to generated value
        """
        generators = {
            PHIType.NAME: self.generate_name,
            PHIType.ADDRESS: self.generate_address,
            PHIType.DATE: self.generate_date,
            PHIType.PHONE: self.generate_simple_phone,
            PHIType.FAX: self.generate_fax,
            PHIType.EMAIL: self.generate_email,
            PHIType.SSN: self.generate_ssn,
            PHIType.MRN: self.generate_mrn,
            PHIType.HEALTH_PLAN_ID: self.generate_health_plan_id,
            PHIType.ACCOUNT_NUMBER: self.generate_account_number,
            PHIType.LICENSE: self.generate_drivers_license,
            PHIType.VEHICLE_ID: self.generate_vehicle_id,
            PHIType.DEVICE_ID: self.generate_device_id,
            PHIType.URL: self.generate_patient_portal_url,
            PHIType.IP_ADDRESS: self.generate_ip_address,
        }

        result = {}
        for phi_type in phi_types:
            if phi_type in generators:
                value = generators[phi_type]()
                result[phi_type] = PHIValue(phi_type=phi_type, value=value)

        return result

    def generate_patient_context(self) -> dict:
        """Generate a complete patient context for note generation."""
        first_name = self.generate_first_name()
        last_name = self.generate_last_name()
        dob = self.generate_dob(min_age=25, max_age=85)

        # Calculate age from DOB
        dob_date = datetime.strptime(dob, "%m/%d/%Y").date()
        today = date.today()
        age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))

        return {
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name} {last_name}",
            "dob": dob,
            "age": age,
            "gender": random.choice(["male", "female"]),
            "ssn": self.generate_ssn(),
            "mrn": self.generate_mrn(),
            "phone": self.generate_simple_phone(),
            "email": self.generate_email(),
            "address": {
                "street": self.generate_street_address(),
                "city": self.generate_city(),
                "state": self.generate_state(),
                "zip": self.generate_zip()
            },
            "emergency_contact": {
                "name": self.generate_name(),
                "phone": self.generate_simple_phone(),
                "relationship": random.choice(["spouse", "parent", "sibling", "child", "friend"])
            },
            "insurance": {
                "plan_id": self.generate_health_plan_id(),
                "provider": random.choice(["Blue Cross Blue Shield", "United Healthcare", "Aetna", "Cigna", "Humana"])
            },
            "drivers_license": self.generate_drivers_license(),
            "provider": {
                "name": self.generate_provider_name(),
                "phone": self.generate_simple_phone(),
                "fax": self.generate_fax()
            },
            "facility": {
                "name": self.generate_hospital_name(),
                "phone": self.generate_simple_phone(),
                "fax": self.generate_fax()
            },
            "encounter_date": self.generate_date(start_year=2024, end_year=2024),
            "encounter_datetime": self.generate_datetime()
        }
