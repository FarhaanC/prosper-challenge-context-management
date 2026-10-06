from common import *
d = pats
for args in [("James Wilson","1984-03-12"),("James Wilson",""),("John Doe","1984-03-12"),("James Wilson","1984-03-13"),
             ("Mr. Wilson","1984-03-12"),("James Wilson Jr","1984-03-12"),("Jim Wilson","1984-03-12"),
             ("James","1984-03-12","WILSON"),("James Wilsen","1984-03-12","W I L S E N"),("James Smith","1984-03-12","WILSON"),
             ("Mei Wang","1995-09-25"),("Mei Wang","1995-09-25","WANG"),("Robert Tyler","1962-05-08"),("Robert Tyler","1962-05-08","TYLOR"),
             ("James Wilson","12/03/1984"),("James Wilson","1984-3-12"),("Emily Braun","1988-01-19"),("Emily Braun","1988-01-19","BRAUN"),
             ("Sarah Jonson","1975-07-30"),("Ahmed","1991-11-02","KHAN"),("Wilson James","1984-03-12")]:
    print(args, "->", d.lookup(*args).status)
print("--- IdentityCheck sequence")
ic = IdentityCheck()
for a in [("James Wilson","1984-03-13"),("James Wilson","1984-03-14"),("James Wilson","1984-03-12"),("James Wilson","1984-03-15","WILSON"),("James Wilson","1984-03-12"),("James Wilson","1984-03-12","WILSON")]:
    s = ic.attempt(d, *a); print(a, "->", s.status, ic.failed_tries)
