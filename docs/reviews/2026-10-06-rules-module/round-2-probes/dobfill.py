import clinic.patients as P
_orig = P.PatientDirectory.lookup
def lookup(self, name, date_of_birth=None):
    if date_of_birth is None:
        m = self._name_matches(name)
        if len(m) == 1:
            date_of_birth = m[0]["date_of_birth"]
    return _orig(self, name, date_of_birth)
P.PatientDirectory.lookup = lookup
