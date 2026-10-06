from common import *
H=["near Geary","near Market","Geary","Market","near Bryant","near Main","near Mission","near the Mission","near Mission Street","near Geary Street",
   "close to Geary","by Market","around Market","Market area","near Bryant Street","the one near Geary","on Geary","near Van Ness","near Lombard","near Union",
   "near Main St","near 4455 Geary","4455 Geary","near 4293 Geary Blvd","9999 Geary Blvd","near 9999 Geary","4455","near 4455","near the Marina","near Marin",
   "near Sunset Boulevard","near Market Street please","near the park","Golden Gate","near Golden Gate Park","near the Presidio","by the bay","near the bay","near Bay",
   "near Dogpatch","near Castro District","Castro","the Castro one","near SF","in SF","SF","San Francisco","the city","I don't mind","no preference","anywhere","doesn't matter",
   "anywhere is fine","nowhere","near nothing","Mission","Mission Bay","Mision Bay","Richmund","Richmond District","the Marina District","Marin","St Mary's","St Mary's Clinic",
   "Mission St","481 Mission St","4874 Main St","main","the main one","Main Street","on Main","near Hayes","Hayes Valley","near Hayes Valley","the Hayes Valley one",
   "North","near North","Union Square","Union","near Union Square","Civic","Downtown","near downtown","the downtown one","Downtown SF","the Midtown one in SF","mid town","Midtown",
   "near Midtown","Outer Sunset","Inner Richmond","the Inner Richmond one","Sunset","near Twin Peaks","Bryant","the one on Bryant","Bryant St","944 Bryant St","4671 Bryant Street",
   "near Fishermans Wharf","near Fisherman's Wharf","by Embarcadero","near the Embarcadero","Financial District","near the financial district","FiDi","SoMa","near soma","near Noe","near Noe Valley","Noe Valley",
   "near the Geary one","near Geary and Market","Geary or Market","near Market and Geary","Market Street or Geary"]
for h in H:
    m=cat.resolve_place(h)
    print(f"{h!r:32} {m.kind:10} near={m.near!s:5} {m.label} {m.location_ids}")
