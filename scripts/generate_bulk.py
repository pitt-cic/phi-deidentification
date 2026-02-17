#!/usr/bin/env python3
"""
CLI script for bulk generation of clinical notes using templates or Faker (no LLM).

Usage:
    # Generate from templates (recommended - uses LLM-generated templates)
    python generate_bulk.py --template-dir templates/ --count 1000

    # Generate from built-in templates (no LLM required)
    python generate_bulk.py --type all --count 500 --seed 42
"""

import argparse
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from string import Template

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import NoteType, PHIType
from src.phi_generator import PHIGenerator


def fill_template(template_content: str, phi_gen: PHIGenerator) -> tuple:
    """
    Fill a template with PHI placeholders.

    Args:
        template_content: Template text with {{PLACEHOLDER}} format
        phi_gen: PHI generator for creating values

    Returns:
        Tuple of (filled_content, phi_entities_list)
    """
    # Generate all PHI values
    patient_context = phi_gen.generate_patient_context()

    # Map placeholders to values
    placeholder_map = {
        "NAME": patient_context['full_name'],
        "FIRST_NAME": patient_context['first_name'],
        "LAST_NAME": patient_context['last_name'],
        "DOB": patient_context['dob'],
        "AGE": str(patient_context['age']),
        "GENDER": patient_context['gender'],
        "SSN": patient_context['ssn'],
        "MRN": patient_context['mrn'],
        "PHONE": patient_context['phone'],
        "EMAIL": patient_context['email'],
        "ADDRESS": patient_context['address']['street'],
        "CITY": patient_context['address']['city'],
        "STATE": patient_context['address']['state'],
        "ZIP": patient_context['address']['zip'],
        "DRIVERS_LICENSE": patient_context['drivers_license'],
        "HEALTH_PLAN_ID": patient_context['insurance']['plan_id'],
        "ACCOUNT_NUMBER": phi_gen.generate_account_number(),
        "EMERGENCY_CONTACT_NAME": patient_context['emergency_contact']['name'],
        "EMERGENCY_CONTACT_PHONE": patient_context['emergency_contact']['phone'],
        "PROVIDER_NAME": patient_context['provider']['name'],
        "PROVIDER_PHONE": patient_context['provider']['phone'],
        "PROVIDER_FAX": patient_context['provider']['fax'],
        "FACILITY_NAME": patient_context['facility']['name'],
        "FACILITY_PHONE": patient_context['facility']['phone'],
        "DATE": patient_context['encounter_date'],
        "ENCOUNTER_DATE": patient_context['encounter_date'],
        "DEVICE_ID": phi_gen.generate_device_id(),
        "IP_ADDRESS": phi_gen.generate_ip_address(),
        "URL": phi_gen.generate_patient_portal_url(),
        "FAX": phi_gen.generate_fax(),
        "VEHICLE_ID": phi_gen.generate_vehicle_id(),
        "LICENSE_PLATE": phi_gen.generate_license_plate(),
    }

    # Fill template and track PHI positions
    filled_content = template_content
    phi_entities = []

    # Find all placeholders and replace them
    pattern = r'\{\{([A-Z_]+)\}\}'

    def replace_and_track(match):
        placeholder = match.group(1)
        if placeholder in placeholder_map:
            value = placeholder_map[placeholder]
            return str(value)
        return match.group(0)  # Keep unrecognized placeholders as-is

    filled_content = re.sub(pattern, replace_and_track, template_content)

    # Now find positions of all PHI values in filled content
    phi_type_map = {
        "NAME": PHIType.NAME,
        "FIRST_NAME": PHIType.NAME,
        "LAST_NAME": PHIType.NAME,
        "DOB": PHIType.DATE,
        "AGE": PHIType.DATE,
        "SSN": PHIType.SSN,
        "MRN": PHIType.MRN,
        "PHONE": PHIType.PHONE,
        "EMAIL": PHIType.EMAIL,
        "ADDRESS": PHIType.ADDRESS,
        "CITY": PHIType.ADDRESS,
        "STATE": PHIType.ADDRESS,
        "ZIP": PHIType.ADDRESS,
        "DRIVERS_LICENSE": PHIType.LICENSE,
        "HEALTH_PLAN_ID": PHIType.HEALTH_PLAN_ID,
        "ACCOUNT_NUMBER": PHIType.ACCOUNT_NUMBER,
        "EMERGENCY_CONTACT_NAME": PHIType.NAME,
        "EMERGENCY_CONTACT_PHONE": PHIType.PHONE,
        "PROVIDER_NAME": PHIType.NAME,
        "PROVIDER_PHONE": PHIType.PHONE,
        "PROVIDER_FAX": PHIType.FAX,
        "FACILITY_NAME": PHIType.OTHER,
        "FACILITY_PHONE": PHIType.PHONE,
        "DATE": PHIType.DATE,
        "ENCOUNTER_DATE": PHIType.DATE,
        "DEVICE_ID": PHIType.DEVICE_ID,
        "IP_ADDRESS": PHIType.IP_ADDRESS,
        "URL": PHIType.URL,
        "FAX": PHIType.FAX,
        "VEHICLE_ID": PHIType.VEHICLE_ID,
    }

    for placeholder, value in placeholder_map.items():
        if not value or len(str(value)) < 2:
            continue
        value_str = str(value)
        phi_type = phi_type_map.get(placeholder, PHIType.OTHER)
        pattern = re.escape(value_str)
        for match in re.finditer(pattern, filled_content):
            phi_entities.append({
                "type": phi_type.value,
                "value": value_str,
                "start": match.start(),
                "end": match.end()
            })

    phi_entities.sort(key=lambda e: e["start"])
    return filled_content, phi_entities


def load_templates(template_dir: Path) -> list:
    """Load all template files from a directory."""
    templates = []
    for template_path in sorted(template_dir.glob("*.txt")):
        manifest_path = template_dir.parent / "manifests" / f"{template_path.stem}.json"

        template_data = {
            "id": template_path.stem,
            "content": template_path.read_text(),
            "note_type": "unknown"
        }

        # Try to load manifest for note type
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                template_data["note_type"] = manifest.get("note_type", "unknown")
            except:
                pass

        templates.append(template_data)

    return templates


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bulk generate clinical notes using Faker (no LLM)"
    )
    parser.add_argument(
        "--template-dir",
        type=str,
        default=None,
        help="Directory containing LLM-generated templates (from generate_notes.py --template)"
    )
    parser.add_argument(
        "-t", "--type",
        type=str,
        default="all",
        help="Note type(s) when using built-in templates: emergency_dept, discharge_summary, "
             "progress_note, radiology_report, telehealth_consult, all"
    )
    parser.add_argument(
        "-c", "--count",
        type=int,
        default=100,
        help="Number of notes to generate per template/type (default: 100)"
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


# Built-in simple templates (fallback if no LLM templates provided)
BUILTIN_TEMPLATES = {
    NoteType.EMERGENCY_DEPT: """
EMERGENCY DEPARTMENT NOTE

Date: {{DATE}}
Time: {{ENCOUNTER_TIME}}

PATIENT INFORMATION:
Name: {{NAME}}
DOB: {{DOB}} (Age: {{AGE}} years)
MRN: {{MRN}}
SSN: {{SSN}}
Address: {{ADDRESS}}, {{CITY}}, {{STATE}} {{ZIP}}
Phone: {{PHONE}}
Email: {{EMAIL}}
Driver's License: {{DRIVERS_LICENSE}}

Emergency Contact: {{EMERGENCY_CONTACT_NAME}}
Contact Phone: {{EMERGENCY_CONTACT_PHONE}}

Insurance: {{HEALTH_PLAN_ID}}

CHIEF COMPLAINT:
Patient presents with abdominal pain.

HISTORY OF PRESENT ILLNESS:
{{NAME}} is a {{AGE}}-year-old {{GENDER}} who presents to the emergency department with abdominal pain. The patient reports symptoms began 2 days ago. Patient denies associated symptoms.

PAST MEDICAL HISTORY:
Hypertension, Type 2 Diabetes Mellitus

MEDICATIONS:
Lisinopril 10mg daily, Metformin 500mg BID

ALLERGIES:
No Known Drug Allergies

PHYSICAL EXAMINATION:
Vital Signs: BP 130/85, HR 78, RR 16, Temp 98.6F, SpO2 98%
General: Alert and oriented, no acute distress
Abdomen: Soft, mild tenderness in RLQ, no rebound

ASSESSMENT AND PLAN:
1. Abdominal pain - likely gastroenteritis
   - IV fluids, antiemetics PRN
   - Labs pending
   - Follow up with PCP

{{NAME}} was counseled regarding diagnosis and treatment plan. Patient verbalized understanding. The patient can be reached at {{PHONE}} if there are any questions.

Attending Physician: {{PROVIDER_NAME}}
Phone: {{PROVIDER_PHONE}}

{{FACILITY_NAME}} Emergency Department
""",

    NoteType.DISCHARGE_SUMMARY: """
DISCHARGE SUMMARY

Patient: {{NAME}}
DOB: {{DOB}}
MRN: {{MRN}}
SSN: {{SSN}} (for billing purposes)

Admission Date: {{DATE}}
Discharge Date: {{DATE}}
Length of Stay: 3 days

Attending Physician: {{PROVIDER_NAME}}
Facility: {{FACILITY_NAME}}

PRINCIPAL DIAGNOSIS:
Community-acquired pneumonia

SECONDARY DIAGNOSES:
Hypertension, Type 2 Diabetes Mellitus

HOSPITAL COURSE:
{{NAME}} is a {{AGE}}-year-old {{GENDER}} admitted with community-acquired pneumonia. Patient was treated with IV antibiotics and supportive care. Clinical status improved over the course of hospitalization.

PROCEDURES PERFORMED:
Chest X-ray, Blood cultures

DISCHARGE MEDICATIONS:
1. Amoxicillin 500mg TID x 7 days
2. Lisinopril 10mg daily
3. Metformin 500mg BID

DISCHARGE INSTRUCTIONS:
{{NAME}} is discharged to home at {{ADDRESS}}, {{CITY}}, {{STATE}} {{ZIP}}.
Activity: As tolerated
Diet: Regular diet
Follow-up: Schedule appointment with {{PROVIDER_NAME}} within 1 week. Call {{PROVIDER_PHONE}} to schedule.
Return to ED if: fever, worsening symptoms, chest pain, difficulty breathing

For questions, the patient or family ({{EMERGENCY_CONTACT_NAME}}) can call {{PROVIDER_PHONE}} or {{FACILITY_PHONE}}.
Records can be faxed to PCP at {{PROVIDER_FAX}}.

Insurance: {{HEALTH_PLAN_ID}}

Dictated by: {{PROVIDER_NAME}}
""",

    NoteType.PROGRESS_NOTE: """
DAILY PROGRESS NOTE

Date: {{DATE}}

Patient: {{NAME}}
DOB: {{DOB}}
MRN: {{MRN}}
Hospital Day: 2
Attending: {{PROVIDER_NAME}}

SUBJECTIVE:
{{NAME}} reports feeling better today, slept well overnight. No acute events overnight.

OBJECTIVE:
Vital Signs: BP 128/82, HR 72, RR 14, Temp 98.2F, SpO2 99%
I/O: 2000mL / 1500mL
Physical Exam:
General: NAD. Lungs: CTAB. CV: RRR. Abd: Soft, NT.
Labs: WBC 8.2, Hgb 12.1, Cr 1.0

ASSESSMENT:
Improving pneumonia on antibiotics

PLAN:
1. Continue current treatment
2. Monitor closely
3. Anticipate discharge tomorrow if stable

Discussed with {{NAME}} and family (contacted {{EMERGENCY_CONTACT_NAME}} at {{EMERGENCY_CONTACT_PHONE}}) regarding plan of care.

{{PROVIDER_NAME}}
{{FACILITY_NAME}}
""",

    NoteType.RADIOLOGY_REPORT: """
RADIOLOGY REPORT

Patient: {{NAME}}
DOB: {{DOB}}
MRN: {{MRN}}
Accession Number: RAD-{{ACCOUNT_NUMBER}}
Account Number: {{ACCOUNT_NUMBER}}

Date of Study: {{DATE}}

Ordering Physician: {{PROVIDER_NAME}}
Phone: {{PROVIDER_PHONE}}

EXAMINATION: CT Chest with contrast

CLINICAL HISTORY:
Cough, shortness of breath

TECHNIQUE:
Helical CT of the chest performed with IV contrast administration.
Performed on GE Revolution CT scanner, Device ID: {{DEVICE_ID}}

COMPARISON:
No prior studies available for comparison.

FINDINGS:
Lungs: Patchy consolidation in the right lower lobe consistent with pneumonia. No pleural effusion.
Heart: Normal size. No pericardial effusion.
Mediastinum: No significant lymphadenopathy.
Bones: No acute osseous abnormality.

IMPRESSION:
1. Right lower lobe pneumonia.
2. No pleural effusion or other acute findings.

Report reviewed and signed electronically by:
{{PROVIDER_NAME}}, MD
{{FACILITY_NAME}} Radiology Department
Phone: {{FACILITY_PHONE}} | Fax: {{PROVIDER_FAX}}
""",

    NoteType.TELEHEALTH_CONSULT: """
TELEHEALTH CONSULTATION NOTE

Date: {{DATE}}

PATIENT INFORMATION:
Name: {{NAME}}
DOB: {{DOB}}
MRN: {{MRN}}
Phone: {{PHONE}}
Email: {{EMAIL}}
Address: {{ADDRESS}}, {{CITY}}, {{STATE}} {{ZIP}}

VISIT TYPE: Video Telehealth Consultation

TECHNOLOGY:
Platform: {{FACILITY_NAME}} Patient Portal ({{URL}})
Connection Status: Successful
Patient IP Address: {{IP_ADDRESS}}
Video/Audio Quality: Good

PATIENT LOCATION:
{{NAME}} is connecting from their home at {{ADDRESS}}, {{CITY}}, {{STATE}}.

IDENTITY VERIFICATION:
Patient identity verified by visual confirmation and verbal verification of name ({{NAME}}) and date of birth ({{DOB}}).

CHIEF COMPLAINT:
Medication refill request

HISTORY OF PRESENT ILLNESS:
{{NAME}} is a {{AGE}}-year-old {{GENDER}} presenting via telehealth for routine follow-up and medication refill. Patient reports blood pressure has been well controlled. No new symptoms.

REVIEW OF SYSTEMS:
Constitutional: No fever, chills, or unintentional weight loss.
Cardiovascular: No chest pain, palpitations.
Respiratory: No shortness of breath, cough.

ASSESSMENT AND PLAN:
1. Hypertension - well controlled
   - Continue Lisinopril 10mg daily
   - Refill provided for 90 days

FOLLOW-UP:
Patient can access visit summary via patient portal at {{URL}}.
For questions, contact our office at {{PROVIDER_PHONE}} or fax at {{FAX}}.
{{NAME}} can also be reached at {{PHONE}} or {{EMAIL}}.

Provider: {{PROVIDER_NAME}}
{{FACILITY_NAME}}
"""
}


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

    output_dir = Path(args.output)
    notes_dir = output_dir / "notes"
    manifests_dir = output_dir / "manifests"
    notes_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    phi_gen = PHIGenerator(seed=args.seed)

    print(f"Output directory: {output_dir.absolute()}")

    templates_to_use = []

    if args.template_dir:
        # Load LLM-generated templates
        template_dir = Path(args.template_dir)
        if not template_dir.exists():
            print(f"Error: Template directory not found: {template_dir}")
            sys.exit(1)

        # Check for templates in notes subdirectory
        notes_subdir = template_dir / "notes"
        if notes_subdir.exists():
            template_dir = notes_subdir

        templates = load_templates(template_dir)
        if not templates:
            print(f"Error: No templates found in {template_dir}")
            sys.exit(1)

        print(f"Loaded {len(templates)} templates from {template_dir}")
        templates_to_use = templates
    else:
        # Use built-in templates
        note_types = get_note_types(args.type)
        if not note_types:
            print("Error: No valid note types specified")
            sys.exit(1)

        for nt in note_types:
            if nt in BUILTIN_TEMPLATES:
                templates_to_use.append({
                    "id": nt.value,
                    "content": BUILTIN_TEMPLATES[nt],
                    "note_type": nt.value
                })

        print(f"Using {len(templates_to_use)} built-in templates")

    print(f"Count per template: {args.count}")
    print("-" * 60)

    total_generated = 0
    note_counter = 1

    for template in templates_to_use:
        template_id = template["id"]
        template_content = template["content"]
        note_type = template["note_type"]

        print(f"\nGenerating {args.count} notes from template: {template_id}")

        for i in range(args.count):
            # Generate unique note ID
            prefix = note_type[:2].upper() if note_type != "unknown" else "NT"
            note_id = f"{prefix}_{note_counter:06d}"

            # Fill template with PHI
            filled_content, phi_entities = fill_template(template_content, phi_gen)

            # Add encounter time placeholder handling
            filled_content = filled_content.replace(
                "{{ENCOUNTER_TIME}}",
                f"{random.randint(0, 23):02d}:{random.randint(0, 59):02d}"
            )

            # Save note
            note_path = notes_dir / f"{note_id}.txt"
            note_path.write_text(filled_content)

            # Save manifest
            manifest = {
                "note_id": note_id,
                "note_type": note_type,
                "generated_at": datetime.now().isoformat(),
                "source_template": template_id,
                "phi_entities": phi_entities
            }
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
