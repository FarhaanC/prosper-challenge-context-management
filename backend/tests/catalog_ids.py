"""Fixed values used by the builder's tests: a fixed "now", and catalog ids with names.

Kept out of conftest.py on purpose: the independent tests have their own
conftest.py, and importing constants "from conftest" would clash between the
two folders when both run in one pytest command.
"""

from datetime import datetime

# Tuesday 6 Oct 2026, 9 AM: a fixed "now" so every run sees the same open times.
NOW = datetime(2026, 10, 6, 9, 0)

SKIN_CANCER_SCREENING = "appt_027"
ANNUAL_PHYSICAL = "appt_002"
KNEE_MRI = "appt_065"
MOLE_REMOVAL = "appt_029"         # Dermatology, needs a referral
WELL_WOMAN_EXAM = "appt_041"      # OB/GYN; for a returning caller only Dr. Linda Nguyen does it
OBGYN_TYPES = ["appt_040", "appt_041", "appt_042", "appt_043", "appt_044"]
NO_DOCTOR_TYPES = ["appt_045", "appt_046", "appt_047", "appt_048", "appt_049", "appt_070", "appt_071", "appt_077"]

MISSION_BAY, MISSION_DISTRICT, NORTH_BEACH, NORTH_GATE = "loc_000", "loc_001", "loc_002", "loc_003"
DOWNTOWN, MIDTOWN, SUNSET, RICHMOND = "loc_004", "loc_005", "loc_006", "loc_007"

DANIEL_CHEN_DERM = "prov_001"      # Dermatology: Downtown, Richmond; takes new patients; English, Arabic
KENJI_KIM_DERM = "prov_027"        # Dermatology: North Beach, Downtown, Midtown, Sunset; Spanish
DANIEL_SMITH_DERM = "prov_035"     # Dermatology: Mission District, Richmond; Spanish
WEI_SATO_DERM = "prov_048"         # Dermatology; NOT taking new patients
LINDA_RAMIREZ_RADIOLOGY = "prov_014"
HANNAH_NGUYEN = "prov_015"
GRACE_RODRIGUEZ = "prov_010"

JAMES_WILSON = ("James Wilson", "1984-03-12")   # Radiology + Orthopedics referrals
EMILY_BROWN = ("Emily Brown", "1988-01-19")     # no referrals
