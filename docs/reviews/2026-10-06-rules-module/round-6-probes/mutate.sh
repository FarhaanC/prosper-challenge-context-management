#!/bin/bash
# Sanity check that the new tests can fail: copy the backend, apply one small change to the
# code, run one test file, report the count. Usage: ./mutate.sh <file> <python-replace-old> <new> <testfile>
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
M="$HERE/mut"; rm -rf "$M"; cp -r "$HERE/../work/backend" "$M"
python3 - "$M/clinic/$1" "$2" "$3" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read(); assert old in s, old; open(p, "w").write(s.replace(old, new, 1))
PY
cd "$M" && timeout 600 python3 -m pytest -q -p no:cacheprovider "tests_independent/$4" 2>&1 | tail -1
