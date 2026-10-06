from common import *
from clinic.options import _doctor_wishes
for h in ["Dr. Dan Chen","Dr. Sam Kim","Dr. Li","Dr. Lee","Dr. Chen Wei","Dr. Wei","Dr. Mike Sato","Dr. Liz Nguyen","Dr. Nguyen","Dr. Chen","Dr. Patty Hernandez","Dr. Garcia","Dr. Kim", "Dr. Smith", "Dr. Danny Chen", "Dr. Tom Hernandez", "Dr. Daniel", "Dr. Linda", "Doctor Maria"]:
    ms = cat.match_providers(h)
    w, n = _doctor_wishes(cat, Preferences(doctor_name_heard=h))
    print(f"{h!r:22} {len(ms)} matches [{', '.join(m.provider.name for m in ms)[:120]}]")
    for x in n: print("     NOTE", x.kind, "|", x.say)
# Dr. Dan Chen in full find_options for skin check
skin = vt("Skin Cancer Screening")
r = find_options(cat, sch, NEW, skin, Preferences(doctor_name_heard="Dr. Dan Chen"), NOW); print("find_options Dan Chen skin:"); show(r)
r = find_options(cat, sch, NEW, skin, Preferences(doctor_name_heard="Dr. Chen"), NOW); print("find_options Dr. Chen skin:"); show(r)
