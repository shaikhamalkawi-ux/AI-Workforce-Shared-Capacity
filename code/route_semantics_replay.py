from pathlib import Path
import pandas as pd
import numpy as np
import networkx as nx
import hashlib, json

HERE = Path(__file__).resolve().parent.parent
INPUT = HERE / "data_public"
OUT = HERE / "replay_outputs"
OUT.mkdir(exist_ok=True)
RHOS = [0.25, 0.50, 0.75, 1.00]
EXPECTED_EMSI_SHA256 = "29534756d3fbe234b0c89551b4c7407293d653cc4577ff567f0bbeb1e97eb2fb"

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def reconstruct():
    emsi_path = INPUT/"Emsi_dataset.csv"
    if sha256(emsi_path) != EXPECTED_EMSI_SHA256:
        raise RuntimeError("Emsi source hash mismatch")
    emsi = pd.read_csv(emsi_path, dtype={"oesCode_origin":str,"oesCode_dest":str})
    if emsi.shape != (256831, 28):
        raise RuntimeError(f"Unexpected Emsi shape {emsi.shape}")
    emsi["order"] = pd.to_numeric(emsi["order"], errors="coerce")
    origins_df = pd.read_csv(INPUT/"baseline_positive_any_support_origins.csv", dtype={"soc":str})
    origins = list(origins_df.soc)
    bls24 = pd.read_csv(INPUT/"BLS2024_34_vectors_used.csv", dtype={"soc":str}).set_index("soc")
    bls25 = pd.read_csv(INPUT/"BLS2025_35_vectors_used.csv", dtype={"soc":str}).set_index("soc")
    code_set = set(bls24.index)
    eo = emsi[emsi.oesCode_origin.isin(origins)].copy()
    cross = eo[eo.oesCode_origin.str[:2] != eo.oesCode_dest.str[:2]].copy()

    released = cross[(cross["order"]<=5) & cross.oesCode_dest.isin(code_set)].sort_values(["oesCode_origin","order"])
    conditioned = cross.sort_values(["oesCode_origin","order"]).groupby("oesCode_origin",group_keys=False).head(5)
    conditioned = conditioned[conditioned.oesCode_dest.isin(code_set)].sort_values(["oesCode_origin","order"])
    joinable = cross[cross.oesCode_dest.isin(code_set)].sort_values(["oesCode_origin","order"]).groupby("oesCode_origin",group_keys=False).head(5)

    menus = {
        "released_no_backfill": released,
        "conditioned_no_backfill": conditioned,
        "fully_joinable_backfill": joinable,
    }

    frozen = pd.read_csv(INPUT/"frozen_released_top5_edges.csv", dtype=str)
    fset = set(map(tuple, frozen[["origin_soc","destination_soc"]].values))
    rset = set(map(tuple, released[["oesCode_origin","oesCode_dest"]].drop_duplicates().values))
    if rset != fset:
        raise RuntimeError(f"335-edge regression gate failed: reconstructed={len(rset)} frozen={len(fset)}")

    return origins, bls24, bls25, menus

def flow_stats(origins, menu_df, supply, openings, rho):
    edges = menu_df[["oesCode_origin","oesCode_dest"]].drop_duplicates()
    denom = float(sum(float(supply[o]) for o in origins))
    independent = 0.0
    for o,g in edges.groupby("oesCode_origin"):
        independent += min(float(supply[o]), sum(rho*float(openings[d]) for d in g.oesCode_dest.unique()))
    G=nx.DiGraph(); S="__S__"; T="__T__"; INF=denom*10+1
    for o in origins:
        G.add_edge(S,"o:"+o,capacity=float(supply[o]))
    for r in edges.itertuples(index=False):
        G.add_edge("o:"+r.oesCode_origin,"d:"+r.oesCode_dest,capacity=INF)
    for d in edges.oesCode_dest.unique():
        G.add_edge("d:"+d,T,capacity=rho*float(openings[d]))
    joint,_ = nx.maximum_flow(G,S,T,flow_func=nx.algorithms.flow.preflow_push)
    deficiency=denom-joint
    return {
        "supply_k":denom,
        "independent_k":independent,
        "joint_k":joint,
        "independent_pct":100*independent/denom,
        "joint_pct":100*joint/denom,
        "gap_pp":100*(independent-joint)/denom,
        "competition_share_of_deficiency":(independent-joint)/deficiency if deficiency>1e-10 else np.nan,
    }

def main():
    origins, bls24, bls25, menus = reconstruct()
    rows=[]; structures=[]
    for name,df in menus.items():
        e=df[["oesCode_origin","oesCode_dest","order","occ_title_origin","occ_title_dest"]].drop_duplicates()
        e=e.rename(columns={"oesCode_origin":"origin_soc","oesCode_dest":"destination_soc"})
        e.to_csv(OUT/f"{name}_edges.csv",index=False)
        structures.append({"menu":name,"edges":len(e),"origins_with_edge":e.origin_soc.nunique(),"destinations":e.destination_soc.nunique()})
    for vintage, bls, tc in [("2024-34",bls24,"transfers_k"),("2025-35",bls25,"transfer_k")]:
        supply=bls[tc].to_dict(); openings=bls["openings_k"].to_dict()
        for name,df in menus.items():
            for rho in RHOS:
                r=flow_stats(origins,df,supply,openings,rho)
                r.update(vintage=vintage,menu=name,rho=rho)
                rows.append(r)
    result=pd.DataFrame(rows)
    numcols=["supply_k","independent_k","joint_k","independent_pct","joint_pct","gap_pp","competition_share_of_deficiency"]
    for c in numcols:
        result[c]=pd.to_numeric(result[c],errors="coerce")
        result.loc[result[c].abs()<5e-10,c]=0.0
        result[c]=result[c].round(10)
    result.to_csv(OUT/"systemA_route_semantics_competition_gap_grid.csv",index=False)
    pd.DataFrame(structures).to_csv(OUT/"systemA_route_menu_structure.csv",index=False)
    print("ROUTE_SEMANTICS_REPLAY: PASS")
    print(result[result.rho.eq(0.5)][["vintage","menu","independent_pct","joint_pct","gap_pp"]].to_string(index=False))

if __name__=="__main__":
    main()
