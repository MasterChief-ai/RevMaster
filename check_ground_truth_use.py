from pathlib import Path
import sys

SKIP_DIRS = {".venv", "venv", "__pycache__", "node_modules", ".git"}

def allowed(p):
    return p.name in {"seed.py", "check_ground_truth_use.py"} or p.name.startswith("eval_")

bad = []
for p in Path(".").rglob("*.py"):
    if any(part in SKIP_DIRS for part in p.parts) or allowed(p):
        continue
    if "ground_truth" in p.read_text(encoding="utf-8", errors="ignore"):
        bad.append(str(p))

if bad:
    print("MISMATCH: these files mention ground_truth:", *bad, sep="\n  ")
    sys.exit(1)
print("OK: no analyzer file mentions ground_truth")