from pathlib import Path
import pandas as pd, hashlib, subprocess, sys, shutil

HERE=Path(__file__).resolve().parent.parent
OUT=HERE/"replay_outputs"
EXPECTED=HERE/"outputs"

subprocess.run([sys.executable, str(HERE/"code"/"route_semantics_replay.py")], check=True)

for fn in ["systemA_route_semantics_competition_gap_grid.csv","systemA_route_menu_structure.csv"]:
    a=(OUT/fn).read_bytes()
    b=(EXPECTED/fn).read_bytes()
    if a!=b:
        raise RuntimeError(f"Replay mismatch: {fn}")
print("PHASE1_BYTE_REPLAY: PASS")
