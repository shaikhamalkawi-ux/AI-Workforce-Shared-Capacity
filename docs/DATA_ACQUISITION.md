# Acquire the DOL/Emsi Career Pathways source

The route-semantics replay requires the U.S. Department of Labor public-use Career Pathways file `Emsi_dataset.csv`.

Expected source identity:
- rows: 256,831
- variables: 28
- SHA-256: `29534756d3fbe234b0c89551b4c7407293d653cc4577ff567f0bbeb1e97eb2fb`

Place the verified file at `data_public/Emsi_dataset.csv` before running:

`python code/verify_phase1_replay.py`

The file is omitted from this distribution to avoid duplicating the large public-use source. Reacquisition plus exact hash verification is required for a fresh route reconstruction.
