from pathlib import Path
import csv, hashlib, sys
root=Path(__file__).resolve().parents[1]
manifest=root/"manifests"/"REPOSITORY_SHA256.csv"
ok=True
with manifest.open(newline="",encoding="utf-8") as f:
    for row in csv.DictReader(f):
        p=root/row["path"]
        if not p.is_file():
            print("MISSING", row["path"]); ok=False; continue
        h=hashlib.sha256(p.read_bytes()).hexdigest()
        if h != row["sha256"]:
            print("MISMATCH", row["path"]); ok=False
print("REPOSITORY_MANIFEST: PASS" if ok else "REPOSITORY_MANIFEST: FAIL")
sys.exit(0 if ok else 1)
