"""
Import hospitals and doctors data from CSV files to Supabase database.
"""
import csv
import os
from supabase import create_client, Client
from dotenv import load_dotenv
from uuid import UUID

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env file")

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def import_hospitals(csv_file_path: str):
    """
    Import hospitals from CSV file.
    CSV Format: id,name
    """
    print(f"\n📥 Importing hospitals from {csv_file_path}...")

    with open(csv_file_path, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        hospitals_data = []

        for row in reader:
            hospital_id = row['id'].strip()
            hospital_name = row['name'].strip()

            if not hospital_id or not hospital_name:
                continue

            hospital_data = {
                'hospital_name': hospital_name,
                'hospital_code': hospital_id,  # Using CSV id as hospital_code
                'is_active': True
            }
            hospitals_data.append(hospital_data)

        # Insert hospitals in batch
        if hospitals_data:
            try:
                result = supabase.table('hospitals').upsert(
                    hospitals_data,
                    on_conflict='hospital_code'
                ).execute()
                print(f"✅ Successfully imported {len(hospitals_data)} hospitals")
                return result.data
            except Exception as e:
                print(f"❌ Error importing hospitals: {e}")
                return None
        else:
            print("⚠️  No hospitals to import")
            return None


def import_doctors(csv_file_path: str, hospital_mapping: dict):
    """
    Import doctors from CSV file.
    CSV Format: onehat_doctor_id,hospital_id,username,full_name,email,specialty,id

    We'll use:
    - id: doctor UUID (already exists in CSV)
    - full_name: doctor's name
    - email: doctor's email
    - specialty: specialization
    - hospital_id: will be mapped to our hospital UUID using hospital_code

    Ignoring: onehat_doctor_id, username (as requested)
    """
    print(f"\n📥 Importing doctors from {csv_file_path}...")

    with open(csv_file_path, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        doctors_data = []
        skipped = 0

        for row in reader:
            # Extract fields
            doctor_id = row['id'].strip()
            full_name = row['full_name'].strip()
            email = row['email'].strip()
            specialty = row.get('specialty', '').strip()
            hospital_code = row['hospital_id'].strip()

            if not doctor_id or not full_name or not email:
                skipped += 1
                continue

            # Look up hospital UUID from hospital_code
            hospital_uuid = hospital_mapping.get(hospital_code)

            doctor_data = {
                'id': doctor_id,  # Use existing UUID from CSV
                'full_name': full_name,
                'email': email,
                'specialization': specialty if specialty else None,
                'hospital_id': hospital_uuid,
                'is_active': True
            }
            doctors_data.append(doctor_data)

        # Insert doctors in batch
        if doctors_data:
            try:
                result = supabase.table('doctors').upsert(
                    doctors_data,
                    on_conflict='id'  # Use id as conflict resolution
                ).execute()
                print(f"✅ Successfully imported {len(doctors_data)} doctors")
                if skipped > 0:
                    print(f"⚠️  Skipped {skipped} invalid rows")
                return result.data
            except Exception as e:
                print(f"❌ Error importing doctors: {e}")
                return None
        else:
            print("⚠️  No doctors to import")
            return None


def get_hospital_mapping():
    """
    Fetch all hospitals and create a mapping of hospital_code -> UUID
    """
    try:
        result = supabase.table('hospitals').select('id, hospital_code').execute()
        mapping = {row['hospital_code']: row['id'] for row in result.data if row['hospital_code']}
        print(f"📊 Loaded {len(mapping)} hospital mappings")
        return mapping
    except Exception as e:
        print(f"❌ Error fetching hospital mapping: {e}")
        return {}


def main():
    """
    Main import function
    """
    print("=" * 60)
    print("🚀 Starting data import process")
    print("=" * 60)

    # Define CSV file paths (relative to project root)
    hospitals_csv = "/Users/karthi/Documents/AI Projects/AI-live-recorder/Hospitals.csv"
    doctors_csv = "/Users/karthi/Documents/AI Projects/AI-live-recorder/doctors_rows (2).csv"

    # Step 1: Import hospitals first
    hospitals_result = import_hospitals(hospitals_csv)

    if not hospitals_result:
        print("❌ Failed to import hospitals. Cannot proceed with doctors import.")
        return

    # Step 2: Get hospital mapping
    hospital_mapping = get_hospital_mapping()

    # Step 3: Import doctors
    doctors_result = import_doctors(doctors_csv, hospital_mapping)

    print("\n" + "=" * 60)
    print("✨ Data import process completed!")
    print("=" * 60)

    # Print summary
    if hospitals_result:
        print(f"📊 Hospitals imported: {len(hospitals_result)}")
    if doctors_result:
        print(f"👨‍⚕️ Doctors imported: {len(doctors_result)}")


if __name__ == "__main__":
    main()
