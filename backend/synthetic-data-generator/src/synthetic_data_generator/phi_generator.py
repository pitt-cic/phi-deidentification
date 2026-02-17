"""PHI value generator using Faker library."""

import random
from datetime import date, datetime, timedelta
from typing import Dict, List, Literal, Optional

import phonenumbers
from faker import Faker
from nicknames import NickNamer

from .models.note_models import PHIType, PHIValue


class PHIGenerator:
    """Generate realistic PHI values using Faker."""

    def __init__(self, seed: Optional[int] = None):
        self.fake = Faker('en_US')
        self.nickname = NickNamer()
        if seed is not None:
            Faker.seed(seed)
            random.seed(seed)

    def generate_name(self, gender: Literal["male", "female", "non_binary"] | None = None) -> dict[str, str]:
        """Generate a full name object with optional middle name and nickname."""
        name = {}
        if gender == "male":
            name["first_name"] = self.fake.first_name_male()
            name["last_name"] = self.fake.last_name_male()
        elif gender == "female":
            name["first_name"] = self.fake.first_name_female()
            name["last_name"] = self.fake.last_name_female()
        elif gender == "non_binary":
            name["first_name"] = self.fake.first_name_nonbinary()
            name["last_name"] = self.fake.last_name_nonbinary()
        else:
            name["first_name"] = self.fake.first_name()
            name["last_name"] = self.fake.last_name()

        name["full_name"] = f"{name['first_name']} {name['last_name']}"

        nickname_choice = random.randint(0, 1)
        if nickname_choice == 1:
            name["nickname"] = self.generate_nickname(name["first_name"])

        return name

    def generate_first_name(self) -> str:
        """Generate a first name."""
        return self.fake.first_name()

    def generate_middle_name(self):
        return self.fake.middle_name()

    def generate_last_name(self) -> str:
        """Generate a last name."""
        return self.fake.last_name()

    def generate_nickname(self, first_name: str) -> str:
        """Generate a nickname for a given first name. If no nicknames are available, return None."""
        nicknames = self.nickname.nicknames_of(first_name)
        if len(nicknames) == 0:
            return ''
        return random.choice(list(nicknames))

    @staticmethod
    def generate_gender() -> Literal["male", "female", "non_binary"]:
        return random.choice(["male", "female", "non_binary"])

    # TODO: Leave out city or states
    def generate_address(self) -> str:
        """Generate a full street address in various formats."""
        # Randomly choose an address format
        format_choice = random.randint(1, 5)

        if format_choice == 1:
            # Format 1: "street, city, state zip" (comma-separated)
            street = self.fake.street_address().replace('\n', ', ')
            return f"{street}, {self.fake.city()}, {self.fake.state_abbr()} {self.fake.zipcode()}"

        elif format_choice == 2:
            # Format 2: "street | city, state zip" (pipe separator)
            street = self.fake.street_address().replace('\n', ' ')
            return f"{street} | {self.fake.city()}, {self.fake.state_abbr()} {self.fake.zipcode()}"

        elif format_choice == 3:
            # Format 3: "number street, city state zip" (single line)
            return f"{self.fake.building_number()} {self.fake.street_name()} {self.fake.street_suffix()}, {self.fake.city()} {self.fake.state_abbr()} {self.fake.zipcode()}"

        elif format_choice == 4:
            # Format 4: "street / city / state / zip" (slash-separated)
            street = self.fake.street_address().replace('\n', ' ')
            return f"{street} / {self.fake.city()} / {self.fake.state()} / {self.fake.zipcode()}"

        else:
            # Format 5: "street; city, state zip" (semicolon separator)
            street = self.fake.street_address().replace('\n', ' ')
            return f"{street}; {self.fake.city()}, {self.fake.state_abbr()} {self.fake.zipcode()}"

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
    
    def generate_date(self, start_year: int = 1950, end_year: int = 2024) -> str:
        """Generate a date in various formats."""
        start_date = date(start_year, 1, 1)
        end_date = date(end_year, 12, 31)
        random_date = self.fake.date_between(start_date=start_date, end_date=end_date)

        return random_date.strftime(self._get_random_date_format())

    def generate_dob(self, min_age: int = 18, max_age: int = 90) -> tuple[str, str]:
        """Generate a date of birth for a person of given age range."""
        today = date.today()
        start_date = today - timedelta(days=max_age * 365)
        end_date = today - timedelta(days=min_age * 365)
        dob = self.fake.date_between(start_date=start_date, end_date=end_date)
        date_format = self._get_random_date_format()
        return dob.strftime(date_format), date_format
    
    def _get_random_date_format(self) -> str:
        """Return a random date format string."""
        date_formats = [
            "%m/%d/%Y",      # 05/16/2021
            "%d/%m/%Y",      # 16/05/2021
            "%Y-%m-%d",      # 2021-05-16
            "%B %d, %Y",     # May 16, 2021 (full month)
            "%d %B %Y",      # 16 May 2021 (full month)
            "%b %d, %Y",     # May 16, 2021 (abbreviated month)
            "%m-%d-%Y",      # 05-16-2021
            "%Y/%m/%d",      # 2021/05/16
            "%d %B, %Y",     # 16 May, 2021 (full month with comma)
            "%B %d %Y",      # May 16 2021 (full month, no comma)
            "%d-%B-%Y",      # 16-May-2021 (full month with hyphens)
        ]
        return date_formats[random.randint(0, len(date_formats) - 1)]

    def generate_datetime(self) -> str:
        """Generate a datetime string."""
        dt = self.fake.date_time_this_year()
        return dt.strftime("%m/%d/%Y %H:%M")
    
    def generate_phone(self) -> str:
        """Generate a phone number."""
        phone_number = self.fake.phone_number()
        try:
            parsed_phone_number = phonenumbers.parse(phone_number)
            format_choice = random.randint(0, 2)

            if parsed_phone_number.extension:
                phone_number_no_ext = phonenumbers.PhoneNumber(country_code=parsed_phone_number.country_code, national_number=parsed_phone_number.national_number)
                phone_number = phonenumbers.format_number(phone_number_no_ext, format_choice)
            else:
                phone_number = phonenumbers.format_number(parsed_phone_number, format_choice)

            return phone_number

        except phonenumbers.phonenumberutil.NumberParseException:
            return phone_number


    # def generate_simple_phone(self) -> str:
    #     """Generate a simple phone number format."""
    #     return f"{self.fake.random_int(200, 999)}-{self.fake.random_int(100, 999)}-{self.fake.random_int(1000, 9999)}"

    def generate_fax(self) -> str:
        """Generate a fax number."""
        return f"{self.fake.random_int(200, 999)}-{self.fake.random_int(100, 999)}-{self.fake.random_int(1000, 9999)}"

    def generate_email(self) -> str:
        """Generate an email address."""
        return self.fake.email()

    def generate_email_domain(self) -> str:
        return self.fake.domain_name()

    def generate_ssn(self) -> str:
        """Generate a Social Security Number."""
        format_choice = random.randint(1, 3)
        if format_choice == 1:
            return self.fake.ssn()
        elif format_choice == 2:
            return self.fake.ssn().replace('-', ' ')
        else:
            return self.fake.ssn().replace('-', '')

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

    @staticmethod
    def generate_vehicle_id() -> str:
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
        return {}
        # generators = {
        #     PHIType.NAME: self.generate_name,
        #     PHIType.ADDRESS: self.generate_address,
        #     PHIType.DATE: self.generate_date,
        #     PHIType.PHONE: self.generate_simple_phone,
        #     PHIType.FAX: self.generate_fax,
        #     PHIType.EMAIL: self.generate_email,
        #     PHIType.SSN: self.generate_ssn,
        #     PHIType.MRN: self.generate_mrn,
        #     PHIType.HEALTH_PLAN_ID: self.generate_health_plan_id,
        #     PHIType.ACCOUNT_NUMBER: self.generate_account_number,
        #     PHIType.LICENSE: self.generate_drivers_license,
        #     PHIType.VEHICLE_ID: self.generate_vehicle_id,
        #     PHIType.DEVICE_ID: self.generate_device_id,
        #     PHIType.URL: self.generate_patient_portal_url,
        #     PHIType.IP_ADDRESS: self.generate_ip_address,
        # }
        #
        # result = {}
        # for phi_type in phi_types:
        #     if phi_type in generators:
        #         value = generators[phi_type]()
        #         result[phi_type] = PHIValue(phi_type=phi_type, value=value)
        #
        # return result

    def generate_patient_context(self) -> dict:
        """Generate a complete patient context for note generation."""
        gender = PHIGenerator.generate_gender()
        name = self.generate_name(gender)
        dob, date_format = self.generate_dob(min_age=25, max_age=85)

        # Calculate age from DOB
        dob_date = datetime.strptime(dob, date_format).date()
        today = date.today()
        age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))

        return {
            "first_name": name["first_name"],
            "last_name": name["last_name"],
            "full_name": name["full_name"],
            "nickname": name.get("nickname", ''),
            "dob": dob,
            "age": age,
            "gender": gender,
            "ssn": self.generate_ssn(),
            "mrn": self.generate_mrn(),
            "phone": self.generate_phone(),
            "email": self.generate_email(),
            "address": {
                "street": self.generate_street_address(),
                "city": self.generate_city(),
                "state": self.generate_state(),
                "zip": self.generate_zip()
            },
            "emergency_contact": {
                "name": self.generate_name(),
                "phone": self.generate_phone(),
                "relationship": random.choice(["spouse", "parent", "sibling", "child", "friend"])
            },
            "insurance": {
                "plan_id": self.generate_health_plan_id(),
                "provider": random.choice(["Blue Cross Blue Shield", "United Healthcare", "Aetna", "Cigna", "Humana"])
            },
            "drivers_license": self.generate_drivers_license(),
            "provider": {
                "name": self.generate_provider_name(),
                "phone": self.generate_phone(),
                "fax": self.generate_fax()
            },
            "facility": {
                "name": self.generate_hospital_name(),
                "phone": self.generate_phone(),
                "fax": self.generate_fax()
            },
            "encounter_date": self.generate_date(start_year=2024, end_year=2024),
            "encounter_datetime": self.generate_datetime()
        }
