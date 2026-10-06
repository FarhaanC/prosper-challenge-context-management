from common import *
W=["dermatologist","dermatologists","Dermatologist.","pediatrician","pediatricians","allergist","immunologist","dentist","orthopedist","orthopedician","orthopaedist","psychiatrist","physical therapist","physicaltherapist",
   "cardiologist","neurologist","radiologist","urologist","gastroenterologist","endocrinologist","ophthalmologist","pulmonologist","generalist","general","podiatrist","hematologist","nephrologist","audiologist",
   "physician","gynecologist","gynaecologist","obstetrician","oncologist","rheumatologist","anesthesiologist","pathologist","otolaryngologist","optometrist","psychologist","psychiatry","cardiology","cardiolgy","nuerology",
   "astrology","dermatologst","dermotologist","pediatrist","generist","ENT","ent","ear nose and throat","OBGYN","ob-gyn","ob","gyn","Allergy","Immunology","lab","labs","laboratory","family doctor","GP","internist","internal",
   "physio","physiotherapist","therapist","dental","teeth","eye doctor","cardiologists","neurologists","urology","pulmonary","pulmonologists","orthopedic","orthopedics","orthopaedics","orthopedists","dentists","dermatologys","",
   "cardiologistss","s","ist","ologist","logist","Endocrine","gastro","GI","Psych","family","medicine","internal medicine","family medicine","physical","therapy","pediatric","pedi"]
for w in W: print(f"{w!r:24} -> {cat.match_specialty(w)}")
