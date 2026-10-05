from common import *
for s in ["physician","a physician","doctor","GP","general practitioner","family doctor","primary care","optician","optometrist","eye doctor",
 "gynecologist","gynaecologist","obstetrician","ENT","ear nose throat","dentist","orthopedist","orthopaedic surgeon","psychologist","therapist",
 "physiotherapist","physio","lab test","blood test","radiologist","x-ray","internist","pulmonologist","lung doctor","skin doctor","heart doctor",
 "podiatrist","urologist","neurologist","endocrinologist","gastroenterologist","GI","paediatrician","pediatric","allergy","immunologist",
 "general","physicist","dental","dentistry","oncologist","psychiatrist","cardio","derm","rad","lab","ortho","gyno","peds"]:
    print(f"{s!r:25} -> {cat.match_specialty(s)}")
