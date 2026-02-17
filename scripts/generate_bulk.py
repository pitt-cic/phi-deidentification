#!/usr/bin/env python3
"""
CLI script for bulk generation of clinical notes using Faker (no LLM).

This script uses pre-defined templates and Faker to generate large volumes
of synthetic notes without LLM API costs.

Usage:
    python generate_bulk.py --count 1000 --type all
    python generate_bulk.py --count 500 --type emergency_dept --seed 42
"""

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from string import Template

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import NoteType, GeneratorConfig, PHIType
from src.phi_generator import PHIGenerator


# Template-based note formats (simplified versions for bulk generation)
NOTE_TEMPLATES = {
    NoteType.EMERGENCY_DEPT: Template("""
EMERGENCY DEPARTMENT NOTE

Date: $encounter_date
Time: $encounter_time

PATIENT INFORMATION:
Name: $full_name
DOB: $dob (Age: $age years)
MRN: $mrn
SSN: $ssn
Address: $street, $city, $state $zip
Phone: $phone
Email: $email
Driver's License: $drivers_license

Emergency Contact: $emergency_contact_name ($emergency_contact_relationship)
Contact Phone: $emergency_contact_phone

Insurance: $insurance_provider
Insurance ID: $insurance_id

CHIEF COMPLAINT:
$chief_complaint

HISTORY OF PRESENT ILLNESS:
$full_name is a $age-year-old $gender who presents to the emergency department with $chief_complaint. The patient reports symptoms began $symptom_duration ago. $additional_hpi

PAST MEDICAL HISTORY:
$past_medical_history

MEDICATIONS:
$medications

ALLERGIES:
$allergies

PHYSICAL EXAMINATION:
Vital Signs: BP $bp, HR $hr, RR $rr, Temp $temp, SpO2 $spo2
General: $general_exam
$system_exam

ASSESSMENT AND PLAN:
$assessment

$full_name was counseled regarding diagnosis and treatment plan. Patient verbalized understanding. The patient can be reached at $phone if there are any questions.

Attending Physician: $provider_name
Phone: $provider_phone

$facility_name Emergency Department
"""),

    NoteType.DISCHARGE_SUMMARY: Template("""
DISCHARGE SUMMARY

Patient: $full_name
DOB: $dob
MRN: $mrn
SSN: $ssn (for billing purposes)

Admission Date: $admission_date
Discharge Date: $discharge_date
Length of Stay: $length_of_stay days

Attending Physician: $provider_name
Facility: $facility_name

PRINCIPAL DIAGNOSIS:
$principal_diagnosis

SECONDARY DIAGNOSES:
$secondary_diagnoses

HOSPITAL COURSE:
$full_name is a $age-year-old $gender admitted on $admission_date with $principal_diagnosis. $hospital_course

PROCEDURES PERFORMED:
$procedures

DISCHARGE MEDICATIONS:
$discharge_medications

DISCHARGE INSTRUCTIONS:
$full_name is discharged to home at $street, $city, $state $zip.
Activity: $activity_restrictions
Diet: $diet_instructions
Follow-up: Schedule appointment with $provider_name within $followup_timeframe. Call $provider_phone to schedule.
Return to ED if: $return_precautions

For questions, the patient or family ($emergency_contact_name) can call $provider_phone or $facility_phone.
Records can be faxed to PCP at $provider_fax.

Insurance: $insurance_provider (ID: $insurance_id)

Dictated by: $provider_name
Date: $discharge_date
"""),

    NoteType.PROGRESS_NOTE: Template("""
DAILY PROGRESS NOTE

Date: $encounter_date
Time: $encounter_time

Patient: $full_name
DOB: $dob
MRN: $mrn
Hospital Day: $hospital_day
Attending: $provider_name

SUBJECTIVE:
$full_name reports $subjective_report. $overnight_events

OBJECTIVE:
Vital Signs: BP $bp, HR $hr, RR $rr, Temp $temp, SpO2 $spo2
I/O: $intake_output
Physical Exam:
$physical_exam
Labs: $lab_results

ASSESSMENT:
$assessment

PLAN:
$plan

Discussed with $full_name and family (contacted $emergency_contact_name at $emergency_contact_phone) regarding plan of care.

$provider_name
$facility_name
"""),

    NoteType.RADIOLOGY_REPORT: Template("""
RADIOLOGY REPORT

Patient: $full_name
DOB: $dob
MRN: $mrn
Accession Number: $accession_number
Account Number: $account_number

Date of Study: $encounter_date
Time: $encounter_time

Ordering Physician: $ordering_provider
Phone: $provider_phone

EXAMINATION: $exam_type

CLINICAL HISTORY:
$clinical_history

TECHNIQUE:
$technique
Performed on $scanner_model, Device ID: $device_id

COMPARISON:
$comparison

FINDINGS:
$findings

IMPRESSION:
$impression

Report reviewed and signed electronically by:
$radiologist_name, MD
$facility_name Radiology Department
Phone: $facility_phone | Fax: $provider_fax
"""),

    NoteType.TELEHEALTH_CONSULT: Template("""
TELEHEALTH CONSULTATION NOTE

Date: $encounter_date
Time: $encounter_time

PATIENT INFORMATION:
Name: $full_name
DOB: $dob
MRN: $mrn
Phone: $phone
Email: $email
Address: $street, $city, $state $zip

VISIT TYPE: Video Telehealth Consultation

TECHNOLOGY:
Platform: $facility_name Patient Portal ($patient_portal_url)
Connection Status: Successful
Patient IP Address: $ip_address
Video/Audio Quality: Good

PATIENT LOCATION:
$full_name is connecting from their home at $street, $city, $state.

IDENTITY VERIFICATION:
Patient identity verified by visual confirmation and verbal verification of name ($full_name) and date of birth ($dob).

CHIEF COMPLAINT:
$chief_complaint

HISTORY OF PRESENT ILLNESS:
$full_name is a $age-year-old $gender presenting via telehealth for $chief_complaint. $hpi

REVIEW OF SYSTEMS:
$review_of_systems

ASSESSMENT AND PLAN:
$assessment

FOLLOW-UP:
Patient can access visit summary via patient portal at $patient_portal_url.
For questions, contact our office at $provider_phone or email at $provider_email.
$full_name can also be reached at $phone or $email.

Provider: $provider_name
$facility_name
""")
}


# Clinical content variations for realistic notes
CLINICAL_CONTENT = {
    "chief_complaints": [
        "chest pain", "shortness of breath", "abdominal pain", "headache",
        "back pain", "fever", "cough", "dizziness", "nausea and vomiting",
        "weakness", "fall", "laceration", "allergic reaction"
    ],
    "past_medical_history": [
        "Hypertension, Type 2 Diabetes Mellitus, Hyperlipidemia",
        "Coronary artery disease, COPD, Atrial fibrillation",
        "Asthma, GERD, Anxiety",
        "No significant past medical history",
        "Hypothyroidism, Osteoarthritis, Depression"
    ],
    "medications": [
        "Lisinopril 10mg daily, Metformin 500mg BID, Atorvastatin 20mg daily",
        "Aspirin 81mg daily, Metoprolol 25mg BID, Omeprazole 20mg daily",
        "Levothyroxine 50mcg daily, Ibuprofen PRN",
        "No current medications",
        "Albuterol inhaler PRN, Fluticasone nasal spray daily"
    ],
    "allergies": [
        "NKDA (No Known Drug Allergies)",
        "Penicillin - rash",
        "Sulfa drugs - hives",
        "Codeine - nausea",
        "No known allergies"
    ],
    "diagnoses": [
        "Acute bronchitis",
        "Community-acquired pneumonia",
        "Acute exacerbation of COPD",
        "Urinary tract infection",
        "Cellulitis of lower extremity",
        "Acute gastroenteritis",
        "Lumbar strain",
        "Migraine headache",
        "Atrial fibrillation with RVR",
        "Diabetic ketoacidosis"
    ],
    "exam_types": [
        "CT Chest with contrast",
        "CT Abdomen and Pelvis with contrast",
        "MRI Brain without contrast",
        "X-ray Chest PA and Lateral",
        "Ultrasound Abdomen Complete",
        "CT Head without contrast"
    ],
    "scanners": [
        "Siemens SOMATOM Definition AS+",
        "GE Revolution CT",
        "Philips Brilliance 64",
        "Siemens MAGNETOM Vida 3T",
        "GE Signa Premier 3.0T"
    ]
}


def generate_bulk_note(
    note_type: NoteType,
    phi_gen: PHIGenerator,
    note_number: int
) -> tuple:
    """
    Generate a single note using templates and Faker.

    Returns:
        Tuple of (note_content, manifest_dict)
    """
    # Generate patient context
    ctx = phi_gen.generate_patient_context()

    # Generate note ID
    prefix = note_type.value.upper()[:2]
    note_id = f"{prefix}_{note_number:06d}"

    # Add clinical content
    ctx["chief_complaint"] = random.choice(CLINICAL_CONTENT["chief_complaints"])
    ctx["past_medical_history"] = random.choice(CLINICAL_CONTENT["past_medical_history"])
    ctx["medications"] = random.choice(CLINICAL_CONTENT["medications"])
    ctx["allergies"] = random.choice(CLINICAL_CONTENT["allergies"])
    ctx["principal_diagnosis"] = random.choice(CLINICAL_CONTENT["diagnoses"])
    ctx["secondary_diagnoses"] = random.choice(CLINICAL_CONTENT["diagnoses"])

    # Flatten address
    ctx["street"] = ctx["address"]["street"]
    ctx["city"] = ctx["address"]["city"]
    ctx["state"] = ctx["address"]["state"]
    ctx["zip"] = ctx["address"]["zip"]

    # Flatten emergency contact
    ctx["emergency_contact_name"] = ctx["emergency_contact"]["name"]
    ctx["emergency_contact_phone"] = ctx["emergency_contact"]["phone"]
    ctx["emergency_contact_relationship"] = ctx["emergency_contact"]["relationship"]

    # Flatten insurance
    ctx["insurance_provider"] = ctx["insurance"]["provider"]
    ctx["insurance_id"] = ctx["insurance"]["plan_id"]

    # Flatten provider
    ctx["provider_name"] = ctx["provider"]["name"]
    ctx["provider_phone"] = ctx["provider"]["phone"]
    ctx["provider_fax"] = ctx["provider"]["fax"]

    # Flatten facility
    ctx["facility_name"] = ctx["facility"]["name"]
    ctx["facility_phone"] = ctx["facility"]["phone"]

    # Generate additional context based on note type
    ctx["encounter_time"] = f"{random.randint(0,23):02d}:{random.randint(0,59):02d}"
    ctx["symptom_duration"] = random.choice(["2 hours", "1 day", "3 days", "1 week"])
    ctx["additional_hpi"] = "Patient denies associated symptoms."
    ctx["general_exam"] = "Alert and oriented, no acute distress"
    ctx["system_exam"] = "Cardiovascular: RRR, no murmurs. Lungs: CTAB. Abdomen: Soft, non-tender."
    ctx["assessment"] = f"1. {ctx['principal_diagnosis']}\n   - Continue current management\n   - Follow up as needed"

    # Vitals
    ctx["bp"] = f"{random.randint(110, 150)}/{random.randint(70, 95)}"
    ctx["hr"] = str(random.randint(60, 100))
    ctx["rr"] = str(random.randint(12, 20))
    ctx["temp"] = f"{random.uniform(97.5, 99.5):.1f}F"
    ctx["spo2"] = f"{random.randint(94, 100)}%"

    # Discharge summary specific
    ctx["admission_date"] = phi_gen.generate_date(start_year=2024, end_year=2024)
    ctx["discharge_date"] = ctx["encounter_date"]
    ctx["length_of_stay"] = str(random.randint(1, 7))
    ctx["hospital_course"] = "Patient was admitted and treated with appropriate therapy. Clinical status improved."
    ctx["procedures"] = "None" if random.random() > 0.5 else "IV fluid administration, Blood cultures"
    ctx["discharge_medications"] = ctx["medications"]
    ctx["activity_restrictions"] = "As tolerated"
    ctx["diet_instructions"] = "Regular diet"
    ctx["followup_timeframe"] = random.choice(["1 week", "2 weeks", "1 month"])
    ctx["return_precautions"] = "fever, worsening symptoms, chest pain, difficulty breathing"

    # Progress note specific
    ctx["hospital_day"] = str(random.randint(1, 5))
    ctx["subjective_report"] = "feeling better today, slept well overnight"
    ctx["overnight_events"] = "No acute events overnight."
    ctx["intake_output"] = f"{random.randint(1500, 2500)}mL / {random.randint(1000, 2000)}mL"
    ctx["physical_exam"] = "General: NAD. Lungs: CTAB. CV: RRR. Abd: Soft, NT."
    ctx["lab_results"] = f"WBC {random.uniform(5, 12):.1f}, Hgb {random.uniform(10, 15):.1f}, Cr {random.uniform(0.8, 1.4):.2f}"
    ctx["plan"] = "1. Continue current treatment\n2. Monitor closely\n3. Anticipate discharge tomorrow if stable"

    # Radiology specific
    ctx["accession_number"] = f"RAD-{random.randint(100000, 999999)}"
    ctx["account_number"] = phi_gen.generate_account_number()
    ctx["exam_type"] = random.choice(CLINICAL_CONTENT["exam_types"])
    ctx["ordering_provider"] = phi_gen.generate_provider_name()
    ctx["clinical_history"] = ctx["chief_complaint"]
    ctx["technique"] = "Standard protocol with IV contrast administration."
    ctx["scanner_model"] = random.choice(CLINICAL_CONTENT["scanners"])
    ctx["device_id"] = phi_gen.generate_device_id()
    ctx["comparison"] = "No prior studies available for comparison."
    ctx["findings"] = "No acute abnormality identified. Normal appearance of visualized structures."
    ctx["impression"] = "1. No acute findings.\n2. Clinical correlation recommended."
    ctx["radiologist_name"] = phi_gen.generate_provider_name()

    # Telehealth specific
    ctx["ip_address"] = phi_gen.generate_ip_address()
    ctx["patient_portal_url"] = phi_gen.generate_patient_portal_url()
    ctx["provider_email"] = phi_gen.generate_email()
    ctx["hpi"] = f"Patient reports {ctx['chief_complaint']} for the past {ctx['symptom_duration']}."
    ctx["review_of_systems"] = "Constitutional: No fever, chills. Negative for other reviewed systems."

    # Generate note content
    template = NOTE_TEMPLATES[note_type]
    content = template.safe_substitute(ctx)

    # Build PHI manifest by finding positions
    phi_entities = []
    phi_values_to_track = [
        (ctx["full_name"], PHIType.NAME),
        (ctx["first_name"], PHIType.NAME),
        (ctx["last_name"], PHIType.NAME),
        (ctx["dob"], PHIType.DATE),
        (ctx["ssn"], PHIType.SSN),
        (ctx["mrn"], PHIType.MRN),
        (ctx["phone"], PHIType.PHONE),
        (ctx["email"], PHIType.EMAIL),
        (ctx["drivers_license"], PHIType.LICENSE),
        (ctx["street"], PHIType.ADDRESS),
        (ctx["city"], PHIType.ADDRESS),
        (ctx["zip"], PHIType.ADDRESS),
        (ctx["emergency_contact_name"], PHIType.NAME),
        (ctx["emergency_contact_phone"], PHIType.PHONE),
        (ctx["insurance_id"], PHIType.HEALTH_PLAN_ID),
        (ctx["provider_name"], PHIType.NAME),
        (ctx["provider_phone"], PHIType.PHONE),
        (ctx["provider_fax"], PHIType.FAX),
        (ctx["facility_phone"], PHIType.PHONE),
        (ctx["encounter_date"], PHIType.DATE),
    ]

    # Add note-type specific PHI
    if note_type == NoteType.RADIOLOGY_REPORT:
        phi_values_to_track.extend([
            (ctx["device_id"], PHIType.DEVICE_ID),
            (ctx["account_number"], PHIType.ACCOUNT_NUMBER),
        ])
    elif note_type == NoteType.TELEHEALTH_CONSULT:
        phi_values_to_track.extend([
            (ctx["ip_address"], PHIType.IP_ADDRESS),
            (ctx["patient_portal_url"], PHIType.URL),
        ])

    import re
    for value, phi_type in phi_values_to_track:
        if not value or len(str(value)) < 2:
            continue
        value_str = str(value)
        pattern = re.escape(value_str)
        for match in re.finditer(pattern, content):
            phi_entities.append({
                "type": phi_type.value,
                "value": value_str,
                "start": match.start(),
                "end": match.end()
            })

    phi_entities.sort(key=lambda e: e["start"])

    manifest = {
        "note_id": note_id,
        "note_type": note_type.value,
        "generated_at": datetime.now().isoformat(),
        "phi_entities": phi_entities
    }

    return note_id, content, manifest


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bulk generate clinical notes using Faker (no LLM)"
    )
    parser.add_argument(
        "-t", "--type",
        type=str,
        default="all",
        help="Note type(s) to generate: emergency_dept, discharge_summary, "
             "progress_note, radiology_report, telehealth_consult, all"
    )
    parser.add_argument(
        "-c", "--count",
        type=int,
        default=100,
        help="Number of notes to generate per type (default: 100)"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="output",
        help="Output directory (default: output)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible generation"
    )
    return parser.parse_args()


def get_note_types(type_arg: str) -> list:
    """Parse the type argument into a list of NoteTypes."""
    if type_arg.lower() == "all":
        return list(NoteType)

    type_map = {
        "emergency_dept": NoteType.EMERGENCY_DEPT,
        "discharge_summary": NoteType.DISCHARGE_SUMMARY,
        "progress_note": NoteType.PROGRESS_NOTE,
        "radiology_report": NoteType.RADIOLOGY_REPORT,
        "telehealth_consult": NoteType.TELEHEALTH_CONSULT,
    }

    types = []
    for t in type_arg.lower().split(","):
        t = t.strip()
        if t in type_map:
            types.append(type_map[t])

    return types


def main():
    args = parse_args()

    if args.seed:
        random.seed(args.seed)

    note_types = get_note_types(args.type)
    if not note_types:
        print("Error: No valid note types specified")
        sys.exit(1)

    output_dir = Path(args.output)
    notes_dir = output_dir / "notes"
    manifests_dir = output_dir / "manifests"
    notes_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output directory: {output_dir.absolute()}")
    print(f"Note types: {[nt.value for nt in note_types]}")
    print(f"Count per type: {args.count}")
    print("-" * 60)

    phi_gen = PHIGenerator(seed=args.seed)

    total_generated = 0
    note_counter = 1

    for note_type in note_types:
        print(f"\nGenerating {args.count} {note_type.value} notes...")
        for i in range(args.count):
            note_id, content, manifest = generate_bulk_note(note_type, phi_gen, note_counter)

            # Save note
            note_path = notes_dir / f"{note_id}.txt"
            note_path.write_text(content)

            # Save manifest
            manifest_path = manifests_dir / f"{note_id}.json"
            manifest_path.write_text(json.dumps(manifest, indent=2))

            note_counter += 1
            total_generated += 1

            if (i + 1) % 100 == 0:
                print(f"  Generated {i + 1}/{args.count}...")

    print("\n" + "=" * 60)
    print(f"Total notes generated: {total_generated}")
    print(f"Notes saved to: {notes_dir}")
    print(f"Manifests saved to: {manifests_dir}")


if __name__ == "__main__":
    main()
