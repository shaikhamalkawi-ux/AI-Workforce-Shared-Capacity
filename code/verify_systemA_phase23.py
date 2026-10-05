from pathlib import Path
import csv,json,hashlib,sys
ROOT=Path(__file__).resolve().parent.parent
REF=ROOT/'outputs'; NEW=ROOT/'replay_outputs'; INP=ROOT/'data_public'
expected={
'baseline_positive_any_support_origins.csv':'6466bdedd3133b5699e3d67af3d367218629aa3a3fdcd9f24da87a7166f61e41',
'frozen_released_top5_edges.csv':'27e1af92e98aa63613f1f1585c660dbc99c132bc101b4ca8fd64286f4c5b7772',
'BLS2024_34_vectors_used.csv':'5a0db47b27af76ff818d370fb770c819d4903ddd3a0ad92c238f53f615fdf199',
'BLS2025_35_vectors_used.csv':'f51c27be680265114951acc66f55e2fd6312f913e4f388f363c2da669d2f578b'}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for n,h in expected.items():
    g=sha(INP/n)
    if g!=h: raise SystemExit(f'INPUT HASH FAIL {n}: {g} != {h}')
files=['destination_mincut_classification_all_vintages_rho.csv','origin_optimal_face_2024-34_rho050.csv','origin_optimal_face_2025-35_rho050.csv','destination_mincut_2024-34_rho050.csv','destination_mincut_2025-35_rho050.csv']
for n in files:
    a=(REF/n).read_bytes(); b=(NEW/n).read_bytes()
    if a!=b: raise SystemExit(f'REPLAY MISMATCH {n}')
print('PHASE2_PHASE3_CLEAN_REPLAY: PASS')
