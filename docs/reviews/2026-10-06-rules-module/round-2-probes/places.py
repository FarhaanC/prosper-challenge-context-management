from common import *
for h in ["the main one","the main clinic","your main office","main","none","no preference","any","anywhere","any location",
 "doesn't matter","on the way to downtown","Northgate","the Northgate one","Outer Richmond","Inner Sunset","near Market Street",
 "the one on Market","Mission Dolores","near the Mission","Bryant","the one on Bryant Street","near Bryant","in the city",
 "San Francisco","SF","the Marina","Marina District","near the marina","Union Square","the Union Square one","Midtown","mid town",
 "down town","the downtown one","near downtown please","Down Town Health","the north beach one","the sunset one","Sunset District",
 "near Sutter Street","Geary","near Geary","near Twin Peaks","by the park","near the hospital","the closest one","nearest",
 "close to me","near my house","Daly City","Oakland","Berkeley","the Bay","bay","the bay area","main street","near Main Street",
 "the Richmond","the Richmond one","Richmond","Mission Bay","Missionbay","mission bey","Hayes","Hayes Valley","near hayes",
 "the castro one","Noe","none of them","no","nob hill","knob hill","Potrero","the Presidio","pacific heights","Fisherman's Wharf",
 "the wharf","Embarcadero","financial district","FiDi","the financial district one","near Chinatown","China town","soma","South of Market",
 "the Tenderloin","civic centre","Civic Center","near Civic Center","western addition","Haight","the haight","Dogpatch","dog patch","bayview","Bay View",
 "Lake Merced","near the airport","the one by the ocean","Ocean Beach","Golden Gate","the gate","Gate","near the Golden Gate Bridge","Market","Main"]:
    m = cat.resolve_place(h)
    print(f"{h!r:35} -> {m.kind:9} near={m.near!s:5} {m.label}")
