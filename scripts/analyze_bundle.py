#!/usr/bin/env python3
"""
Analyze a Synthea FHIR bundle to identify encounter types and template opportunities.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


def analyze_bundle(bundle_path):
    with open(bundle_path, 'r') as f:
        bundle = json.load(f)

    # Count resources by type
    resource_counts = defaultdict(int)
    encounters = []
    doc_refs = []
    patients = []
    conditions = []
    procedures = []
    medications = []
    imaging_studies = []

    for entry in bundle.get('entry', []):
        resource = entry.get('resource', {})
        res_type = resource.get('resourceType', 'Unknown')
        resource_counts[res_type] += 1

        if res_type == 'Encounter':
            encounters.append(resource)
        elif res_type == 'DocumentReference':
            doc_refs.append(resource)
        elif res_type == 'Patient':
            patients.append(resource)
        elif res_type == 'Condition':
            conditions.append(resource)
        elif res_type == 'Procedure':
            procedures.append(resource)
        elif res_type == 'MedicationRequest':
            medications.append(resource)
        elif res_type == 'ImagingStudy':
            imaging_studies.append(resource)

    print("=" * 80)
    print("SYNTHEA BUNDLE ANALYSIS")
    print("=" * 80)
    print(f"\nBundle: {bundle_path}")
    print(f"Total entries: {len(bundle.get('entry', []))}")

    print("\n## Resource Counts:")
    for res_type, count in sorted(resource_counts.items(), key=lambda x: -x[1]):
        print(f"  {res_type}: {count}")

    # Analyze encounter types
    print("\n" + "=" * 80)
    print("ENCOUNTER ANALYSIS (Potential Note Templates)")
    print("=" * 80)

    encounter_types = defaultdict(list)
    for enc in encounters:
        enc_type = enc.get('type', [{}])[0].get('coding', [{}])[0]
        enc_class = enc.get('class', {}).get('code', 'unknown')
        reason = enc.get('reasonCode', [{}])[0].get('coding', [{}])[0].get('display', 'N/A') if enc.get('reasonCode') else 'N/A'

        key = (enc_type.get('code', 'unknown'), enc_type.get('display', 'Unknown'), enc_class)
        encounter_types[key].append({
            'id': enc.get('id'),
            'reason': reason,
            'period': enc.get('period', {})
        })

    print("\n## Encounter Types Found:")
    print("-" * 80)

    template_suggestions = []
    for (code, display, enc_class), encs in sorted(encounter_types.items()):
        print(f"\n### {display}")
        print(f"    Code: {code}")
        print(f"    Class: {enc_class}")
        print(f"    Count: {len(encs)}")
        reasons = set(e['reason'] for e in encs[:5])
        print(f"    Sample reasons: {reasons}")

        # Map to template type
        if code == '50849002':  # Emergency room admission
            template_suggestions.append(('emergency_dept', display, len(encs)))
        elif code == '308646001':  # Death certification
            template_suggestions.append(('death_certificate', display, len(encs)))
        elif enc_class == 'ambulatory':
            template_suggestions.append(('progress_note', display, len(encs)))
        elif enc_class == 'inpatient':
            template_suggestions.append(('discharge_summary', display, len(encs)))
        elif enc_class == 'wellness':
            template_suggestions.append(('wellness_visit', display, len(encs)))
        else:
            template_suggestions.append(('general_note', display, len(encs)))

    # Analyze DocumentReferences (existing notes)
    print("\n" + "=" * 80)
    print("EXISTING CLINICAL NOTES (DocumentReference)")
    print("=" * 80)

    doc_types = defaultdict(int)
    for doc in doc_refs:
        doc_type = doc.get('type', {}).get('coding', [{}])[0].get('display', 'Unknown')
        doc_types[doc_type] += 1

    print(f"\nTotal DocumentReferences: {len(doc_refs)}")
    print("\n## Document Types:")
    for doc_type, count in sorted(doc_types.items(), key=lambda x: -x[1]):
        print(f"  {doc_type}: {count}")

    # Show sample note content
    if doc_refs:
        print("\n## Sample Note Content (first 500 chars):")
        sample_doc = doc_refs[0]
        if 'content' in sample_doc:
            for content in sample_doc.get('content', []):
                attachment = content.get('attachment', {})
                if 'data' in attachment:
                    import base64
                    try:
                        decoded = base64.b64decode(attachment['data']).decode('utf-8')
                        print("-" * 60)
                        print(decoded[:500])
                        print("..." if len(decoded) > 500 else "")
                        print("-" * 60)
                    except Exception as e:
                        print(f"  [Could not decode: {e}]")

    # Analyze conditions
    print("\n" + "=" * 80)
    print("CONDITIONS (Diagnoses)")
    print("=" * 80)
    print(f"\nTotal Conditions: {len(conditions)}")
    condition_names = [c.get('code', {}).get('coding', [{}])[0].get('display', 'Unknown') for c in conditions[:10]]
    print("\n## Sample Conditions:")
    for cond in condition_names:
        print(f"  - {cond}")

    # Analyze procedures
    print("\n" + "=" * 80)
    print("PROCEDURES")
    print("=" * 80)
    print(f"\nTotal Procedures: {len(procedures)}")
    procedure_names = [p.get('code', {}).get('coding', [{}])[0].get('display', 'Unknown') for p in procedures[:10]]
    print("\n## Sample Procedures:")
    for proc in procedure_names:
        print(f"  - {proc}")

    # Analyze medications
    print("\n" + "=" * 80)
    print("MEDICATIONS")
    print("=" * 80)
    print(f"\nTotal MedicationRequests: {len(medications)}")
    med_names = []
    for med in medications[:10]:
        if 'medicationCodeableConcept' in med:
            med_names.append(med['medicationCodeableConcept'].get('coding', [{}])[0].get('display', 'Unknown'))
    print("\n## Sample Medications:")
    for med in med_names:
        print(f"  - {med}")

    # PHI available in Patient resource
    print("\n" + "=" * 80)
    print("PHI AVAILABLE IN PATIENT RESOURCE")
    print("=" * 80)

    if patients:
        patient = patients[0]
        print("\n## Patient Details:")

        # Name
        if 'name' in patient:
            name = patient['name'][0]
            given = ' '.join(name.get('given', []))
            family = name.get('family', '')
            print(f"  ✓ NAME: {given} {family}")

        # DOB
        if 'birthDate' in patient:
            print(f"  ✓ DOB: {patient['birthDate']}")

        # Gender
        if 'gender' in patient:
            print(f"  ✓ GENDER: {patient['gender']}")

        # Address
        if 'address' in patient:
            addr = patient['address'][0]
            line = ', '.join(addr.get('line', []))
            city = addr.get('city', '')
            state = addr.get('state', '')
            print(f"  ✓ ADDRESS: {line}, {city}, {state}")

        # Telecom
        if 'telecom' in patient:
            for telecom in patient.get('telecom', []):
                system = telecom.get('system', 'unknown')
                value = telecom.get('value', 'N/A')
                print(f"  ✓ {system.upper()}: {value}")

        # Identifiers
        if 'identifier' in patient:
            print("\n## Identifiers:")
            for ident in patient.get('identifier', []):
                id_type = ident.get('type', {}).get('coding', [{}])[0].get('display', 'Unknown')
                value = ident.get('value', 'N/A')
                print(f"  ✓ {id_type}: {value}")

        print("\n## PHI to INJECT (not in Synthea):")
        print("  ○ Email address")
        print("  ○ Fax number")
        print("  ○ IP address")
        print("  ○ URLs (patient portal)")
        print("  ○ Device IDs")
        print("  ○ Account numbers")
        print("  ○ Vehicle IDs")

    # Imaging Studies
    print("\n" + "=" * 80)
    print("IMAGING STUDIES")
    print("=" * 80)
    print(f"\nTotal ImagingStudies: {len(imaging_studies)}")
    if imaging_studies:
        for img in imaging_studies[:3]:
            modality = img.get('modality', [{}])[0].get('display', 'Unknown') if img.get('modality') else 'Unknown'
            print(f"  - Modality: {modality}")

    # Summary and recommendations
    print("\n" + "=" * 80)
    print("TEMPLATE RECOMMENDATIONS")
    print("=" * 80)
    print("\nBased on this bundle, the following templates can be generated:")
    print("-" * 60)

    for template_type, display, count in template_suggestions:
        print(f"  {template_type:<20} (from '{display}', {count} encounters)")

    print("\n## Suggested Note Types for PHI Testing:")
    print("  1. emergency_dept      - Rich PHI: SSN, insurance, emergency contacts, vehicle IDs")
    print("  2. discharge_summary   - PHI: addresses, follow-up contacts, fax numbers")
    print("  3. progress_note       - PHI: names, dates, MRN")
    print("  4. radiology_report    - PHI: device IDs, account numbers")
    print("  5. telehealth_consult  - PHI: IP addresses, URLs, email")

    # Return data for programmatic use
    return {
        'resource_counts': dict(resource_counts),
        'encounter_types': [(code, display, enc_class, len(encs)) for (code, display, enc_class), encs in encounter_types.items()],
        'template_suggestions': template_suggestions,
        'patient_phi': patients[0] if patients else None,
        'has_imaging': len(imaging_studies) > 0
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_bundle.py <path_to_fhir_bundle.json>")
        print("\nExample:")
        print("  python analyze_bundle.py ../synthea-example/Abe604_Frami345_b8dd1798-beef-094d-1be4-f90ee0e6b7d5.json")
        sys.exit(1)

    analyze_bundle(sys.argv[1])
