from common import *
from clinic.catalog import _doctor_words
from clinic.fuzzy import normalize
for s in cat.specialties():
    n=[normalize(s).replace(" ","")]+[normalize(p).replace(" ","") for p in s.split("/")]
    print(s, "->", [w for x in n for w in _doctor_words(x)])
words = "podiatrist|podiatry|hematologist|nephrologist|oncologist|rheumatologist|gynecologist|gynaecologist|obstetrician|gyno|gyn|psychologist|psychiatrist|therapist|physio|physiotherapist|physical therapist|internist|GP|general practitioner|family doctor|eye doctor|optometrist|ophthalmologist|ENT|ear nose and throat|otolaryngologist|cardiologist|heart doctor|skin doctor|dermatologist|dermatology|pediatrician|paediatrician|pediatrist|orthopedist|orthopedic surgeon|orthopaedics|allergist|immunologist|immunology|dentist|dental|radiologist|urologist|neurologist|neurosurgeon|endocrinologist|gastroenterologist|gastro|pulmonologist|lung doctor|lab|labs|laboratory|blood test|generist|general|physician|surgeon|anesthesiologist|audiologist|hepatologist|proctologist|sexologist|cosmetologist|dermatologists|pediatricians|Urologists|neurology|nurology|cardiolgy|pulmonary|respiratory|allergy|ob gyn|OB-GYN|obgyn|women's health|family medicine|internal medicine|primary care".split("|")
for w in words: print(f"{w!r:28} -> {cat.match_specialty(w)}")
