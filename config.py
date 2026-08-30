"""
config.py — Lead Cloud AI Configuration
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
JOBS_DIR = DATA_DIR / "jobs"
USERS_FILE = DATA_DIR / "users.json"
JOBS_FILE = DATA_DIR / "jobs.json"

for d in [DATA_DIR, JOBS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.getenv("SECRET_KEY", "lead-cloud-dev-secret-change-in-production")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")

PORT = int(os.getenv("PORT", "8000"))

NICHE_SEARCH_MAP = {
    "hvac": ["HVAC Contractor", "Air Conditioning Repair", "Heating and Cooling", "AC Installation", "Furnace Repair"],
    "roofing": ["Roofing Contractor", "Roof Repair", "Roof Installation", "Roofing Service"],
    "plumbing": ["Plumbing Contractor", "Plumber", "Pipe Repair", "Drain Cleaning"],
    "pest control": ["Pest Control", "Exterminator", "Termite Control", "Bug Exterminator"],
    "electrical": ["Electrician", "Electrical Contractor", "Wiring Service", "Electrical Repair"],
    "medical": ["Medical Practice", "Doctor Office", "Family Medicine", "Clinic"],
    "dental": ["Dental Clinic", "Dentist", "Dental Office"],
    "restaurant": ["Restaurant", "Food Service", "Catering"],
    "auto repair": ["Auto Repair", "Mechanic", "Car Service", "Auto Shop"],
    "landscaping": ["Landscaping", "Lawn Care", "Garden Service"],
    "cleaning": ["Cleaning Service", "Janitorial", "House Cleaning"],
    "co-packer": ["Co-Packing", "Food Co-Manufacturer", "Private Label Food"],
}

NPI_TAXONOMY_MAP = {
    "medical": ["208D00000X", "207Q00000X", "207R00000X", "208000000X"],
    "dental": ["122300000X"],
}

RATE_LIMIT_PER_CLIENT = 500
MAX_LEADS_PER_REQUEST = 1000
BATCH_SIZES = [10, 25, 50, 100, 200, 500]
