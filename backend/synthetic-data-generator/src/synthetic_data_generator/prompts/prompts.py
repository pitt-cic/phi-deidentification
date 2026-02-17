DISCHARGE_SUMMARY_PROMPT = """
Generate a realistic Hospital Discharge Summary using the following patient information. The note MUST include ALL the PHI values provided below naturally embedded in the clinical narrative. Do not use placeholders - use the exact values given.

PATIENT INFORMATION (use these exact values in the note):
{phi_context}

REQUIREMENTS:
1. Include ALL PHI values naturally within the clinical narrative
2. Follow the standard discharge summary format with sections:
   - Patient Demographics (name, DOB, MRN, SSN for billing)
   - Admission Date and Discharge Date
   - Attending Physician
   - Principal Diagnosis
   - Hospital Course
   - Procedures Performed
   - Discharge Medications
   - Follow-up Instructions (include provider phone/fax numbers)
   - Discharge Condition
3. Mention the patient by name multiple times
4. Include the patient's address in the discharge instructions (e.g., "Patient discharged home at [address]")
5. Include contact numbers for follow-up appointments
6. Reference insurance/health plan information
7. Include emergency contact information in case of questions
8. Include fax number for sending records to PCP
9. Make the clinical scenario realistic (e.g., pneumonia, CHF exacerbation, post-surgical)

Generate a complete discharge summary now. Do not include any instructions or meta-commentary - just the clinical note itself.
"""

EMERGENCY_DEPT_PROMPT = """
Generate a realistic Emergency Department clinical note using the following patient information. The note MUST include ALL the PHI values provided below naturally embedded in the clinical narrative. Do not use placeholders - use the exact values given.

PATIENT INFORMATION (use these exact values in the note):
{phi_context}

REQUIREMENTS:
1. Include ALL PHI values naturally within the clinical narrative
2. The note should follow standard ED documentation format
3. Include: Chief Complaint, History of Present Illness, Past Medical History, Medications, Allergies, Physical Exam, Assessment, and Plan
4. Mention the patient by name multiple times throughout the note
5. Include references to contacting family/emergency contact by phone
6. Reference the patient's address when documenting social history or discharge planning
7. Include the SSN and insurance information in the registration/demographic section
8. Reference the driver's license if relevant (e.g., patient arrived by personal vehicle, MVA, or ID verification)
9. Include all dates and times as provided in the PHI context. Never transform dates or times.
10. Make the clinical scenario realistic and coherent

Generate a complete ED note now. Do not include any instructions or meta-commentary - just the clinical note itself.
"""

PROGRESS_NOTE_PROMPT = """
Generate a realistic Daily Progress Note (SOAP format) using the following patient information. The note MUST include ALL the PHI values provided below naturally embedded in the clinical narrative. Do not use placeholders - use the exact values given.

PATIENT INFORMATION (use these exact values in the note):
{phi_context}

REQUIREMENTS:
1. Include relevant PHI values naturally within the clinical narrative
2. Follow SOAP format:
   - Header: Patient name, MRN, DOB, Date of Service, Attending
   - Subjective: Patient's reported symptoms, overnight events
   - Objective: Vital signs, physical exam findings, lab results
   - Assessment: Clinical impression, problem list
   - Plan: Treatment plan, consultations, anticipated discharge
3. Mention the patient by name in the narrative
4. Include the date and time of the encounter
5. Reference the MRN in the header
6. Include the attending physician's name
7. If relevant, mention calls to family (include phone number)
8. Make it a realistic hospital day (e.g., Day 3 of pneumonia treatment)

Generate a complete progress note now. Do not include any instructions or meta-commentary - just the clinical note itself.
"""

RADIOLOGY_REPORT_PROMPT = """
Generate a realistic Radiology Report using the following patient information. The note MUST include ALL the PHI values provided below naturally embedded in the report. Do not use placeholders - use the exact values given.

PATIENT INFORMATION (use these exact values in the report):
{phi_context}

ADDITIONAL CONTEXT:
- Generate an account/accession number for this study
- Include a realistic device/scanner ID in the technical section
- Choose an appropriate imaging modality (CT, MRI, X-ray, Ultrasound)

REQUIREMENTS:
1. Include relevant PHI values in appropriate sections
2. Follow standard radiology report format:
   - Header: Patient name, MRN, DOB, Accession Number, Date of Study
   - Clinical History/Indication
   - Technique (include scanner/device ID)
   - Comparison (if applicable)
   - Findings (detailed, organ-by-organ)
   - Impression (summary of key findings)
   - Signature block with radiologist name
3. Include the referring physician's name and contact for results
4. Include device identifiers naturally (e.g., "Performed on Siemens SOMATOM Definition AS+ CT scanner, Device ID: [device_id]")
5. Generate a realistic clinical scenario (e.g., chest CT for lung nodule, abdominal CT for appendicitis)
6. Include account number for billing reference

Generate a complete radiology report now. Do not include any instructions or meta-commentary - just the clinical report itself.
"""

TELEHEALTH_CONSULT_PROMPT = """
Generate a realistic Telehealth Consultation Note using the following patient information. The note MUST include ALL the PHI values provided below naturally embedded in the clinical narrative. Do not use placeholders - use the exact values given.

PATIENT INFORMATION (use these exact values in the note):
{phi_context}

TELEHEALTH-SPECIFIC CONTEXT:
- This is a video visit conducted via the patient portal
- Include technical details about the connection
- Generate a realistic IP address for the patient's connection
- Reference the patient portal URL

REQUIREMENTS:
1. Include ALL PHI values naturally within the clinical narrative
2. Follow telehealth documentation format:
   - Header: Patient name, MRN, DOB, Date/Time of Visit
   - Visit Type: Telehealth/Video Visit
   - Technology Used: Document the platform, connection quality
   - Patient Location: Document where patient is connecting from (include address)
   - Patient Identity Verification: How patient was identified
   - Clinical Documentation: Chief complaint, HPI, Assessment, Plan
   - Technical Section: Connection info, IP address, platform URL
3. Mention the patient by name multiple times
4. Include email address (for portal notifications/appointment confirmations)
5. Include phone number (for callback if connection drops)
6. Reference the patient portal URL for follow-up access
7. Include IP address in technical documentation section
8. Document that patient identity was verified (mention name verification)
9. Make it a realistic primary care scenario (e.g., medication refill, chronic disease follow-up)

Generate a complete telehealth consultation note now. Do not include any instructions or meta-commentary - just the clinical note itself.
"""

TEMPLATE_MODE_PROMPT = """
IMPORTANT: Generate this note as a TEMPLATE with placeholders instead of actual PHI values.
Use these exact placeholder formats:
- {{NAME}} for patient name
- {{FIRST_NAME}} for first name only
- {{LAST_NAME}} for last name only
- {{DOB}} for date of birth
- {{AGE}} for age
- {{GENDER}} for gender
- {{SSN}} for Social Security Number
- {{MRN}} for Medical Record Number
- {{PHONE}} for phone numbers
- {{FAX}} for fax numbers
- {{EMAIL}} for email addresses
- {{ADDRESS}} for street address
- {{CITY}} for city
- {{STATE}} for state
- {{ZIP}} for ZIP code
- {{DRIVERS_LICENSE}} for driver's license
- {{HEALTH_PLAN_ID}} for insurance ID
- {{ACCOUNT_NUMBER}} for account numbers
- {{EMERGENCY_CONTACT_NAME}} for emergency contact name
- {{EMERGENCY_CONTACT_PHONE}} for emergency contact phone
- {{PROVIDER_NAME}} for provider name
- {{PROVIDER_PHONE}} for provider phone
- {{PROVIDER_FAX}} for provider fax
- {{FACILITY_NAME}} for facility name
- {{FACILITY_PHONE}} for facility phone
- {{DATE}} for dates
- {{DEVICE_ID}} for device identifiers
- {{IP_ADDRESS}} for IP addresses
- {{URL}} for URLs

**Use the PHI clinical context (conditions, procedures, medications) as-is, but replace all PHI with placeholders.**
"""