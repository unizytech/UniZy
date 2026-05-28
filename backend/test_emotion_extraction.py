"""
Test script for emotion extraction feature.
Tests the complete workflow: scheduling → extraction → saving to database.
"""

import asyncio
import uuid
from datetime import datetime
from services.background_tasks import schedule_emotion_extraction
from services.supabase_service import supabase

# Sample transcript with emotional content for testing
TEST_TRANSCRIPT = """
Doctor: Good morning, how are you feeling today?

Patient: I'm very worried, doctor. I haven't been sleeping well because of these chest pains. I'm really scared it might be my heart. My father had a heart attack at my age.

Doctor: I understand your concern. Let's talk about your symptoms. When did this start?

Patient: About a week ago. The pain comes and goes, but it's been keeping me up at night. I'm anxious about it.

Doctor: I can see you're anxious. Let me examine you and we'll run some tests to be sure. How is your insurance coverage?

Patient: Um, actually, I'm worried about the cost. Can we do just the necessary tests? I don't have the best insurance and money is tight right now.

Doctor: Of course. We'll prioritize the most important ones. Don't worry, we'll work this out. I want to run an ECG and some blood work first.

Patient: Okay, thank you. How much will that cost approximately?

Doctor: The billing department can give you an exact estimate, but we can also discuss payment plans if needed. Your health is the priority.

Patient: Thank you, doctor. I really appreciate that. I feel a bit better knowing there are options.

Doctor: The exam looks good so far. Your heart rate and blood pressure are normal. I'll order the ECG and blood work now. These should give us a clear picture.

Patient: Okay, I feel more reassured now. Thank you for explaining everything and being understanding about the cost concerns.

Doctor: You're welcome. Make sure to follow up with me next week after we get the test results. Do you have any other questions?

Patient: No, I think I'm good. Thank you again, doctor.

Doctor: Take care. We'll get to the bottom of this.
"""

async def test_emotion_extraction():
    """Test the complete emotion extraction workflow."""

    print("\n" + "="*80)
    print("EMOTION EXTRACTION TEST")
    print("="*80 + "\n")

    # Get OP consultation type
    consultation_types = supabase.table('consultation_types').select('*').eq('type_code', 'OP').execute()
    if not consultation_types.data:
        print("❌ ERROR: OP consultation type not found")
        return

    consultation_type = consultation_types.data[0]
    consultation_type_id = uuid.UUID(consultation_type['id'])

    print(f"✓ Found OP consultation type: {consultation_type['type_name']}")
    print(f"  - Emotion analysis enabled: {consultation_type.get('enable_emotion_analysis', False)}")
    print()

    # Get OP_CORE template for database-driven prompts
    templates_response = supabase.table('templates').select('id').eq('template_code', 'OP_CORE').execute()
    if not templates_response.data:
        print("❌ ERROR: OP_CORE template not found")
        return

    template_id = templates_response.data[0]['id']
    print(f"✓ Found OP_CORE template: {template_id}")
    print()

    # Get an existing doctor (or create a test one)
    doctors_response = supabase.table('doctors').select('id').limit(1).execute()

    if doctors_response.data:
        user_id = uuid.UUID(doctors_response.data[0]['id'])
        print(f"✓ Using existing doctor: {user_id}")
    else:
        # Create a test doctor if none exist
        test_doctor = {
            "id": str(uuid.uuid4()),
            "name": "Test Doctor",
            "email": f"test-{uuid.uuid4().hex[:8]}@example.com"
        }
        doctor_response = supabase.table('doctors').insert(test_doctor).execute()
        user_id = uuid.UUID(doctor_response.data[0]['id'])
        print(f"✓ Created test doctor: {user_id}")

    # Get an existing patient (or create a test one)
    patients_response = supabase.table('patients').select('id').limit(1).execute()

    if patients_response.data:
        patient_id = uuid.UUID(patients_response.data[0]['id'])
        print(f"✓ Using existing patient: {patient_id}")
    else:
        # Create a test patient if none exist
        test_patient_uuid = uuid.uuid4()
        test_patient = {
            "id": str(test_patient_uuid),
            "patient_id": f"TEST-MRN-{uuid.uuid4().hex[:8].upper()}",  # External patient ID (MRN)
            "full_name": "Test Patient for Emotion Extraction",
        }
        patient_response = supabase.table('patients').insert(test_patient).execute()
        patient_id = uuid.UUID(patient_response.data[0]['id'])
        print(f"✓ Created test patient: {patient_id}")

    print()

    # Create a test extraction record
    extraction_data = {
        "session_id": None,  # NULL for test (session_id is optional)
        "consultation_type_id": str(consultation_type_id),
        "user_id": str(user_id),  # Using user_id instead of doctor_id
        "patient_id": str(patient_id),
        "extraction_mode": "full",
        "model_used": "gemini-2.5-flash",
        "segment_count": 0,
        "original_extraction_json": {"test": "data"}
    }

    print("Creating test extraction record...")
    extraction_response = supabase.table("medical_extractions").insert(extraction_data).execute()

    if not extraction_response.data:
        print("❌ ERROR: Failed to create extraction record")
        return

    extraction_id = uuid.UUID(extraction_response.data[0]['id'])
    print(f"✓ Created extraction record: {extraction_id}")
    print()

    # Schedule emotion extraction (with shorter delay for testing)
    print("Scheduling emotion extraction with 5-second delay...")
    await schedule_emotion_extraction(
        transcript=TEST_TRANSCRIPT,
        extraction_id=extraction_id,
        consultation_type_id=consultation_type_id,
        delay_seconds=5,  # Shorter for testing
        template_id=template_id,  # Required for database-driven audio prompts
    )

    print("✓ Emotion extraction scheduled")
    print()
    print("Waiting for background task to complete (30 seconds)...")
    print("-" * 80)

    # Wait for extraction to complete
    # (5s delay + ~15-20s for Gemini API call)
    await asyncio.sleep(30)  # Wait 30 seconds total

    print("-" * 80)
    print()

    # Check extraction status
    print("Checking extraction status...")
    status_response = supabase.table('medical_extractions').select('*').eq('id', str(extraction_id)).execute()

    if status_response.data:
        extraction = status_response.data[0]
        print(f"✓ Extraction Status:")
        print(f"  - Started: {extraction.get('emotion_extraction_started', False)}")
        print(f"  - Completed: {extraction.get('emotion_extraction_completed', False)}")
        print(f"  - Failed: {extraction.get('emotion_extraction_failed', False)}")
        if extraction.get('emotion_extraction_error'):
            print(f"  - Error: {extraction['emotion_extraction_error']}")
        print()

    # Check if emotion segments were saved
    print("Checking emotion segments...")
    segments_response = supabase.table('extraction_segments').select('segment_code, segment_value').eq('extraction_id', str(extraction_id)).execute()

    if segments_response.data:
        print(f"✓ Found {len(segments_response.data)} emotion segments:")
        for segment in segments_response.data:
            print(f"\n  📊 {segment['segment_code']}")
            segment_value = segment['segment_value']

            # Display key information based on segment type
            if segment['segment_code'] == 'TEXT_EMOTION_ANXIETY_PRE_CONSULTATION':
                print(f"     Level: {segment_value.get('level', 'N/A')}")
                print(f"     Confidence: {segment_value.get('confidence', 'N/A')}")
                if segment_value.get('indicators'):
                    print(f"     Indicators: {len(segment_value['indicators'])} detected")

            elif segment['segment_code'] == 'TEXT_EMOTION_ANXIETY_POST_CONSULTATION':
                print(f"     Level: {segment_value.get('level', 'N/A')}")
                print(f"     Change: {segment_value.get('change_from_pre', 'N/A')}")
                print(f"     Confidence: {segment_value.get('confidence', 'N/A')}")

            elif segment['segment_code'] == 'TEXT_EMOTION_OTHER_EMOTIONS_DETECTED':
                emotions = segment_value.get('emotions_detected', [])
                print(f"     Emotions: {len(emotions)} detected")
                for emotion in emotions[:3]:  # Show first 3
                    if isinstance(emotion, dict):
                        print(f"       - {emotion.get('emotion', 'Unknown')} ({emotion.get('severity', 'N/A')})")
                    else:
                        print(f"       - {emotion}")

            elif segment['segment_code'] == 'TEXT_EMOTION_FINANCIAL_CONCERNS':
                print(f"     Concerns Present: {segment_value.get('concerns_present', False)}")
                print(f"     Severity: {segment_value.get('severity', 'N/A')}")
                concerns = segment_value.get('specific_concerns', [])
                if concerns:
                    print(f"     Specific Concerns: {len(concerns)}")

            elif segment['segment_code'] == 'TEXT_EMOTION_TREATMENT_COMPLIANCE_LIKELIHOOD':
                print(f"     Likelihood: {segment_value.get('likelihood', 'N/A')}")
                print(f"     Confidence: {segment_value.get('confidence', 'N/A')}")
                positive = segment_value.get('positive_factors', [])
                negative = segment_value.get('negative_factors', [])
                print(f"     Positive Factors: {len(positive)}")
                print(f"     Negative Factors: {len(negative)}")

        print()
    else:
        print("⚠️  No emotion segments found yet (extraction may still be running)")
        print()

    # Cleanup test data
    print("Cleaning up test data...")
    supabase.table('extraction_segments').delete().eq('extraction_id', str(extraction_id)).execute()
    supabase.table('medical_extractions').delete().eq('id', str(extraction_id)).execute()
    print("✓ Test data cleaned up")
    print()

    print("="*80)
    print("TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(test_emotion_extraction())
