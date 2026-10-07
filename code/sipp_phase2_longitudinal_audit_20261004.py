#!/usr/bin/env python3
"""Phase-2 longitudinal SIPP audit for the AI Workforce shared-capacity journal paper.

This script does not rebuild the upstream person-transition construction. It consumes the retained person-transition
file, replicate weights, conservative Census occupation-to-SOC candidate mapping, the
661-SOC analytical frame, and prespecified System-A route objects.

Primary annual worker-mobility definition:
  - primary job valid in Dec-2023 and Dec-2024 (Phase-1 rule),
  - age 18-64 at both endpoints,
  - nonmissing job identifier at both endpoints,
  - different job identifier AND different public-use occupation code.
Strict cross-major mobility further requires Phase-1 DEFINITELY_CROSS_MAJOR == 1.

Raw occupation-code change is retained only as a recoding-sensitive diagnostic.
Mapping concordance preserves one-to-many Census->SOC sets; no title matching or
arbitrary one-to-one allocation is used.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Dict, Iterable, Set, Tuple

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
# Person-level SIPP inputs are intentionally not in this public repository.
# Point SIPP_LOCAL_DIR to a local directory containing the verified public-use extracts.
import os
LOCAL = Path(os.environ.get('SIPP_LOCAL_DIR', REPO / 'local_sipp_inputs'))
TRANSITIONS = LOCAL / 'sipp_2023_2024_person_transitions.csv'
AGE23 = LOCAL / 'sipp_december_2023_age.csv'
AGE24 = LOCAL / 'sipp_december_2024_age.csv'
REPW = LOCAL / 'sipp_2023_2024_replicate_weights.csv.gz.csv'
MAP_EDGES = LOCAL / 'sipp_public_use_to_soc2018_candidate_edges.csv'
FRAME = LOCAL / 'BeyondAIR_Interval_Core_Ledger_661.csv'
SYSTEMA_ORIGINS = REPO / 'data_public/baseline_positive_any_support_origins.csv'
SYSTEMA_EDGES = REPO / 'data_public/frozen_released_top5_edges.csv'
SYSTEMA_SUMMARY = REPO / 'outputs/phase1_route_semantics_summary.json'

OUTDIR = Path(os.environ.get('SIPP_OUTPUT_DIR', REPO / 'local_sipp_outputs'))
OUTDIR.mkdir(parents=True, exist_ok=True)
OUT_RESULTS = OUTDIR / 'SIPP_PHASE2_RESULTS_20261004.json'
OUT_RATES = OUTDIR / 'sipp_phase2_rate_uncertainty.csv'
OUT_CONCORD = OUTDIR / 'sipp_phase2_systemA_concordance.csv'
OUT_CORE = OUTDIR / 'sipp_phase2_core_destination_support.csv'
OUT_EVENTS = OUTDIR / 'sipp_phase2_systemA_event_classification.csv.gz'
# PUBLICATION NOTE: this output contains event-level person rows and is generated only for local audit/reproduction.
# It is intentionally excluded from the public-facing reproducibility archive.

CORE_DESTINATIONS = {
    '11-2022': 'Sales Managers',
    '43-1011': 'First-Line Supervisors of Office and Administrative Support Workers',
    '43-3031': 'Bookkeeping, Accounting, and Auditing Clerks',
    '43-4081': 'Hotel, Motel, and Resort Desk Clerks',
    '43-6014': 'Secretaries and Administrative Assistants, Except Legal, Medical, and Executive',
}

OLD_ADJACENT_MONTH = {
    'all_cross_major_n': 864,
    'all_cross_major_weighted_mass': 10841130.8,
    'mappable_to_661_n': 607,
    'core_destination_events_n': 18,
    'core_destination_weighted_share_pct': 1.64,
    'core_destinations_observed_count': 5,
    'systemB_weighted_bounds_pct': {
        'strict': {'origin_lower': 0.1336, 'origin_upper': 2.6619, 'exact_lower': 0.2214, 'exact_upper': 0.4471},
        'representative': {'origin_lower': 0.6646, 'origin_upper': 6.6879, 'exact_lower': 1.1008, 'exact_upper': 2.9064},
        'loose': {'origin_lower': 2.1724, 'origin_upper': 11.8358, 'exact_lower': 3.5955, 'exact_upper': 6.4380},
    },
}


def weighted_rate(df: pd.DataFrame, flag: str, weight: str) -> float:
    den = df[weight].sum()
    if den <= 0:
        return float('nan')
    return float(df.loc[df[flag].astype(bool), weight].sum() / den)


def fay_brr_rate(df: pd.DataFrame, flag: str, denom_flag: str | None = None) -> Dict[str, float]:
    """Census SIPP Fay BRR, G=240, Fay coefficient=0.5.

    If denom_flag is None, all rows in df form the denominator. Otherwise rows for which
    denom_flag is true form the denominator. REPWGT0 is used for the full estimate.
    """
    if denom_flag is None:
        denmask = np.ones(len(df), dtype=bool)
    else:
        denmask = df[denom_flag].astype(bool).to_numpy()
    nummask = df[flag].astype(bool).to_numpy() & denmask
    w0 = df['REPWGT0'].to_numpy(float)
    theta0 = float(w0[nummask].sum() / w0[denmask].sum())
    reps = []
    for g in range(1, 241):
        w = df[f'REPWGT{g}'].to_numpy(float)
        reps.append(float(w[nummask].sum() / w[denmask].sum()))
    reps = np.asarray(reps)
    var = float(np.sum((reps - theta0) ** 2) / (240 * (0.5 ** 2)))
    se = math.sqrt(var)
    lo = max(0.0, theta0 - 1.96 * se)
    hi = min(1.0, theta0 + 1.96 * se)
    return {'estimate': theta0, 'se': se, 'ci95_low': lo, 'ci95_high': hi}


def build_soc_sets(candidate_edges: pd.DataFrame, frame: Set[str]) -> Dict[int, Set[str]]:
    d: Dict[int, Set[str]] = {}
    for occ, grp in candidate_edges.groupby('public_occ'):
        vals = {str(x).strip() for x in grp['candidate_soc2018'] if str(x).strip() in frame}
        d[int(occ)] = vals
    return d


def event_choices(S: Set[str], D: Set[str], origins: Set[str], edges: Set[Tuple[str, str]]):
    """Return sharp mapping endpoint indicators for one event.

    A mapping choice can contribute (numerator, denominator) = (0,0), (0,1), or (1,1).
    The global lower endpoint chooses denominator-only mappings whenever possible and
    excludes optional route-only denominator events if origin admission can be avoided.
    The global upper endpoint chooses route mappings whenever possible and excludes
    optional denominator-only events if origin admission can be avoided.
    """
    S_in = S & origins
    necessary_origin = bool(S) and S <= origins
    possible_origin = bool(S_in)
    exact_origin = len(S) == 1 and necessary_origin
    admitted_pairs = {(s, d) for s in S_in for d in D}
    route_pairs = admitted_pairs & edges
    any_route = bool(route_pairs)
    all_admitted_route = bool(admitted_pairs) and admitted_pairs <= edges
    any_nonroute_admitted = bool(admitted_pairs - edges)

    lower_num = necessary_origin and all_admitted_route
    lower_den = lower_num or any_nonroute_admitted or (necessary_origin and not D)

    upper_num = any_route
    upper_den = any_route or (necessary_origin and not any_route)

    exact_lower_num = exact_origin and all_admitted_route
    exact_upper_num = exact_origin and any_route

    return {
        'necessary_origin': necessary_origin,
        'possible_origin': possible_origin,
        'exact_origin': exact_origin,
        'any_route': any_route,
        'all_admitted_route': all_admitted_route,
        'lower_num': lower_num,
        'lower_den': lower_den,
        'upper_num': upper_num,
        'upper_den': upper_den,
        'exact_lower_num': exact_lower_num,
        'exact_upper_num': exact_upper_num,
    }


def ratio_from_flags(df: pd.DataFrame, num: str, den: str, weight: str) -> float:
    denv = float(df.loc[df[den], weight].sum())
    return float(df.loc[df[num], weight].sum() / denv) if denv else float('nan')


def fay_brr_ratio_from_flags(df: pd.DataFrame, num: str, den: str) -> Dict[str, float]:
    vals = []
    for g in range(241):
        wcol = f'REPWGT{g}'
        d = float(df.loc[df[den], wcol].sum())
        n = float(df.loc[df[num], wcol].sum())
        vals.append(n / d if d else np.nan)
    theta0 = vals[0]
    reps = np.asarray(vals[1:], dtype=float)
    var = float(np.nansum((reps - theta0) ** 2) / (240 * (0.5 ** 2)))
    se = math.sqrt(var)
    return {
        'estimate': float(theta0), 'se': se,
        'ci95_low': max(0.0, float(theta0 - 1.96*se)),
        'ci95_high': min(1.0, float(theta0 + 1.96*se)),
    }


def main():
    t = pd.read_csv(TRANSITIONS)
    a23 = pd.read_csv(AGE23)
    a24 = pd.read_csv(AGE24)
    rw = pd.read_csv(REPW, compression='gzip')
    map_edges = pd.read_csv(MAP_EDGES)
    frame_df = pd.read_csv(FRAME)
    O = set(pd.read_csv(SYSTEMA_ORIGINS)['soc'].astype(str))
    E = set(map(tuple, pd.read_csv(SYSTEMA_EDGES)[['origin_soc','destination_soc']].astype(str).itertuples(index=False, name=None)))
    sysa_summary = json.load(open(SYSTEMA_SUMMARY, encoding='utf-8'))

    t = t.merge(a23[['SSUID','PNUM','AGE_DEC_2023']], on=['SSUID','PNUM'], how='left', validate='one_to_one')
    t = t.merge(a24[['SSUID','PNUM','AGE_DEC_2024']], on=['SSUID','PNUM'], how='left', validate='one_to_one')
    t['AGE_BOTH_18_64'] = t['AGE_DEC_2023'].between(18,64) & t['AGE_DEC_2024'].between(18,64)
    t['AGE_2024_18_64'] = t['AGE_DEC_2024'].between(18,64)

    rwcols = ['SSUID','PNUM'] + [f'REPWGT{i}' for i in range(241)]
    t = t.merge(rw[rwcols], on=['SSUID','PNUM'], how='left', validate='one_to_one', indicator='_rw_merge')
    primary_rel = (t['PRIMARY_ANALYSIS_INCLUDED'] == 1) & t['AGE_BOTH_18_64']
    assert (t.loc[primary_rel, '_rw_merge'] == 'both').all(), 'Missing replicate weights in primary age-restricted sample.'
    rel = t.loc[primary_rel & t['FINYR2'].notna()]
    assert np.allclose(rel['FINYR2'], rel['REPWGT0'], rtol=1e-10, atol=1e-6)

    t['BOTH_JOBID'] = t['JOBID_2023'].notna() & t['JOBID_2024'].notna()
    t['JOBID_CHANGED'] = t['BOTH_JOBID'] & (t['JOBID_2023'] != t['JOBID_2024'])
    t['STRICT_OCC_JOB_CHANGE'] = t['JOBID_CHANGED'] & (t['OCC_CHANGED'] == 1)
    t['STRICT_CROSS_MAJOR'] = t['STRICT_OCC_JOB_CHANGE'] & (t['DEFINITELY_CROSS_MAJOR'] == 1)

    primary = t[(t['PRIMARY_ANALYSIS_INCLUDED']==1) & t['AGE_BOTH_18_64']].copy()
    jobden = primary[primary['BOTH_JOBID']].copy()

    rate_specs = [
        ('raw_occupation_code_change_diagnostic', primary, 'OCC_CHANGED'),
        ('different_jobid', jobden, 'JOBID_CHANGED'),
        ('strict_occupation_changing_job_transition', jobden, 'STRICT_OCC_JOB_CHANGE'),
        ('strict_definitely_cross_major_transition', jobden, 'STRICT_CROSS_MAJOR'),
    ]
    rate_rows=[]
    for label, df, flag in rate_specs:
        ci=fay_brr_rate(df,flag)
        rate_rows.append({
            'metric':label, 'raw_n':int(df[flag].sum()), 'raw_den_n':int(len(df)),
            'unweighted_pct':100*float(df[flag].mean()), 'weighted_pct':100*weighted_rate(df,flag,'FINYR2'),
            'fay_brr_se_pp':100*ci['se'], 'ci95_low_pct':100*ci['ci95_low'], 'ci95_high_pct':100*ci['ci95_high'],
        })
    strict_job = jobden[jobden['STRICT_OCC_JOB_CHANGE']].copy()
    ci_share=fay_brr_rate(strict_job,'STRICT_CROSS_MAJOR')
    rate_rows.append({
        'metric':'cross_major_share_among_strict_occ_changing_job_transitions',
        'raw_n':int(strict_job['STRICT_CROSS_MAJOR'].sum()), 'raw_den_n':int(len(strict_job)),
        'unweighted_pct':100*float(strict_job['STRICT_CROSS_MAJOR'].mean()),
        'weighted_pct':100*weighted_rate(strict_job,'STRICT_CROSS_MAJOR','FINYR2'),
        'fay_brr_se_pp':100*ci_share['se'],'ci95_low_pct':100*ci_share['ci95_low'],'ci95_high_pct':100*ci_share['ci95_high'],
    })
    rates=pd.DataFrame(rate_rows)
    rates.to_csv(OUT_RATES,index=False)

    sens = {}
    for age_flag in ['AGE_BOTH_18_64','AGE_2024_18_64']:
        sdf=t[(t['PRIMARY_ANALYSIS_INCLUDED']==1)&t[age_flag]&t['BOTH_JOBID']].copy()
        sens[age_flag]={
            'den_n':int(len(sdf)),
            'strict_occ_job_weighted_pct':100*weighted_rate(sdf,'STRICT_OCC_JOB_CHANGE','FINYR2'),
            'strict_cross_major_weighted_pct':100*weighted_rate(sdf,'STRICT_CROSS_MAJOR','FINYR2'),
        }

    frame=set(frame_df['soc'].astype(str))
    socsets=build_soc_sets(map_edges,frame)
    events=jobden[jobden['STRICT_CROSS_MAJOR']].copy()
    choices=[]
    for r in events.itertuples(index=False):
        S=socsets.get(int(r.OCC_2023),set()); D=socsets.get(int(r.OCC_2024),set())
        c=event_choices(S,D,O,E)
        c.update({'source_soc_set':'|'.join(sorted(S)),'dest_soc_set':'|'.join(sorted(D)),'mappable_both_661':bool(S and D)})
        choices.append(c)
    cdf=pd.DataFrame(choices,index=events.index)
    for col in cdf.columns:
        events[col]=cdf[col]
    out_event_cols=['SSUID','PNUM','OCC_2023','OCC_2024','FINYR2','source_soc_set','dest_soc_set','mappable_both_661','necessary_origin','possible_origin','exact_origin','any_route','all_admitted_route','lower_num','lower_den','upper_num','upper_den','exact_lower_num','exact_upper_num']
    events[out_event_cols].to_csv(OUT_EVENTS, index=False, compression='gzip')

    mapped = events.copy()
    mapped['exact_den'] = mapped['exact_origin']
    concord_rows = []
    specs = [
        ('origin_conditioned_lower', 'lower_num','lower_den'),
        ('origin_conditioned_upper', 'upper_num','upper_den'),
        ('exact_origin_lower','exact_lower_num','exact_den'),
        ('exact_origin_upper','exact_upper_num','exact_den'),
    ]
    for label, nf, df in specs:
        val_w = ratio_from_flags(mapped,nf,df,'FINYR2')
        val_u = mapped[nf].sum()/mapped[df].sum()
        ci = fay_brr_ratio_from_flags(mapped,nf,df)
        concord_rows.append({
            'endpoint': label,
            'unweighted_num_n': int(mapped[nf].sum()), 'unweighted_den_n': int(mapped[df].sum()),
            'unweighted_pct': 100*val_u,
            'weighted_numerator_mass': float(mapped.loc[mapped[nf],'FINYR2'].sum()),
            'weighted_denominator_mass': float(mapped.loc[mapped[df],'FINYR2'].sum()),
            'weighted_pct': 100*val_w,
            'fay_brr_se_pp': 100*ci['se'], 'ci95_low_pct': 100*ci['ci95_low'], 'ci95_high_pct': 100*ci['ci95_high'],
        })
    concord = pd.DataFrame(concord_rows)
    concord.to_csv(OUT_CONCORD, index=False)

    core_rows=[]
    strict_job = jobden[jobden['STRICT_OCC_JOB_CHANGE']].copy()
    strict_cross = jobden[jobden['STRICT_CROSS_MAJOR']].copy()
    for soc,title in CORE_DESTINATIONS.items():
        public_codes = sorted({int(x) for x in map_edges.loc[map_edges['candidate_soc2018'].astype(str)==soc,'public_occ']})
        code_mask_job = strict_job['OCC_2024'].isin(public_codes)
        code_mask_cross = strict_cross['OCC_2024'].isin(public_codes)
        core_rows.append({
            'destination_soc': soc, 'destination': title, 'public_occ_codes': ';'.join(map(str,public_codes)),
            'strict_occ_job_n': int(code_mask_job.sum()),
            'strict_occ_job_weight': float(strict_job.loc[code_mask_job,'FINYR2'].sum()),
            'strict_cross_major_n': int(code_mask_cross.sum()),
            'strict_cross_major_weight': float(strict_cross.loc[code_mask_cross,'FINYR2'].sum()),
        })
    core = pd.DataFrame(core_rows)
    core['strict_occ_job_weighted_share_pct'] = 100*core['strict_occ_job_weight']/strict_job['FINYR2'].sum()
    core['strict_cross_major_weighted_share_pct'] = 100*core['strict_cross_major_weight']/strict_cross['FINYR2'].sum()
    core.to_csv(OUT_CORE,index=False)

    core_totals = {
        'strict_occ_job_events_n': int(core['strict_occ_job_n'].sum()),
        'strict_occ_job_weight': float(core['strict_occ_job_weight'].sum()),
        'strict_occ_job_weighted_share_pct': float(100*core['strict_occ_job_weight'].sum()/strict_job['FINYR2'].sum()),
        'strict_cross_major_events_n': int(core['strict_cross_major_n'].sum()),
        'strict_cross_major_weight': float(core['strict_cross_major_weight'].sum()),
        'strict_cross_major_weighted_share_pct': float(100*core['strict_cross_major_weight'].sum()/strict_cross['FINYR2'].sum()),
        'strict_cross_major_unweighted_share_pct': float(100*core['strict_cross_major_n'].sum()/len(strict_cross)),
        'destinations_with_strict_cross_major_support': int((core['strict_cross_major_n']>0).sum()),
    }

    pa_all = t[t['PRIMARY_ANALYSIS_INCLUDED']==1].copy()
    sj = pa_all[pa_all['BOTH_JOBID'] & (pa_all['JOBID_2023']==pa_all['JOBID_2024'])]
    recoding = {
        'same_jobid_n': int(len(sj)),
        'same_jobid_changed_occ_n': int((sj['OCC_CHANGED']==1).sum()),
        'same_jobid_definitely_cross_major_n': int((sj['DEFINITELY_CROSS_MAJOR']==1).sum()),
    }

    rho05 = [x for x in sysa_summary['rho050_results'] if x['vintage']=='2024-34' and x['menu']=='released_no_backfill'][0]
    assert abs(rho05['independent_pct'] - 83.64825581395351) < 1e-10
    assert abs(rho05['joint_pct'] - 49.39599483204132) < 1e-10

    results = {
        'status': 'PHASE2_AUDIT_COMPLETE_SYSTEM_B_ROW_LEVEL_OBJECTS_NOT_INCLUDED',
        'primary_definition': 'Age 18-64 at both Dec endpoints; valid Phase-1 primary jobs; both JOBID present; strict mobility requires different JOBID plus different occupation; strict cross-major requires DEFINITELY_CROSS_MAJOR=1.',
        'counts': {
            'phase1_primary_all_ages_n': int((t['PRIMARY_ANALYSIS_INCLUDED']==1).sum()),
            'primary_age_both_18_64_n': int(len(primary)),
            'both_jobid_age_both_n': int(len(jobden)),
            'strict_occ_job_n': int(jobden['STRICT_OCC_JOB_CHANGE'].sum()),
            'strict_cross_major_n': int(jobden['STRICT_CROSS_MAJOR'].sum()),
            'strict_cross_major_weight': float(jobden.loc[jobden['STRICT_CROSS_MAJOR'],'FINYR2'].sum()),
            'mapped_strict_cross_major_to_661_both_ends_n': int(events['mappable_both_661'].sum()),
            'systemA_necessary_origin_events_n': int(mapped['necessary_origin'].sum()),
            'systemA_possible_origin_events_n': int(mapped['possible_origin'].sum()),
            'systemA_exact_origin_events_n': int(mapped['exact_origin'].sum()),
            'systemA_any_route_events_n': int(mapped['any_route'].sum()),
        },
        'same_jobid_recoding_audit_all_ages': recoding,
        'rates': {r['metric']: r for r in rate_rows},
        'age_2024_only_sensitivity': sens,
        'systemA_concordance': {r['endpoint']: r for r in concord_rows},
        'persistent_receiving_core': {'by_destination': core_rows, 'totals': core_totals},
        'old_adjacent_month_locked_comparator': OLD_ADJACENT_MONTH,
        'systemA_replay_gate': {
            'rho': 0.50,
            'reference_2024_34_independent_pct': rho05['independent_pct'],
            'reference_2024_34_joint_pct': rho05['joint_pct'],
            'reference_2024_34_gap_pp': rho05['gap_pp'],
        },
        'systemB_longitudinal_status': {
            'decision': 'NOT_REPORTED',
            'reason': 'The row-level System-B strict/representative/loose edge ledgers and exact 372-origin SOC list required for a design-identical longitudinal concordance calculation are not included in the publication-safe materials. Aggregate rules and reported structural results are documented; rebuilding from a different release would define a different analysis.',
            'preserved_rules': {
                'strict': 'O*NET Primary-Short; education allowance 0 category; destination median wage >=100% of origin; retain source-directed relation',
                'representative': 'All Primary; education allowance +1 category; destination median wage >=90% of origin; retain source-directed relation',
                'loose': 'Primary + Supplemental; education allowance +2 categories; destination median wage >=80% of origin; retain source-directed relation',
            },
            'locked_edge_counts': {'strict':513,'representative':1658,'loose':3716},
            'locked_destination_counts': {'strict':272,'representative':458,'loose':562},
        },
        'interpretation': {
            'primary_sipp_layer': 'Use one-year Dec-2023 to Dec-2024 strict different-JOBID longitudinal evidence as the primary SIPP layer.',
            'adjacent_month_role': 'Retain the old adjacent-month 2024-reference SIPP layer as short-horizon sensitivity/comparator.',
            'systemA': 'Longitudinal System-A route support is positive but sparse; treat as observed mobility triangulation/boundary evidence, not validation or causal confirmation.',
            'receiving_core': 'Aggregate weighted cross-major support to the five-core set is similar in scale to the old adjacent-month layer, but only two of five core destinations receive strict annual cross-major support; do not claim five-of-five longitudinal confirmation.',
        },
    }
    with open(OUT_RESULTS,'w',encoding='utf-8') as f:
        json.dump(results,f,indent=2,ensure_ascii=False)

    def close(a,b,tol=5e-8):
        assert abs(a-b) <= tol, (a,b)
    rr = rates.set_index('metric')
    close(rr.loc['raw_occupation_code_change_diagnostic','unweighted_pct'], 58.32824893227578)
    close(rr.loc['raw_occupation_code_change_diagnostic','weighted_pct'], 59.55554054895039)
    close(rr.loc['different_jobid','weighted_pct'], 16.65953575050645)
    close(rr.loc['strict_occupation_changing_job_transition','weighted_pct'], 12.19047155694294)
    close(rr.loc['strict_definitely_cross_major_transition','weighted_pct'], 9.718780559981882)
    close(rr.loc['cross_major_share_among_strict_occ_changing_job_transitions','weighted_pct'], 79.72440195053236)
    cc = concord.set_index('endpoint')
    close(cc.loc['origin_conditioned_lower','weighted_pct'], 3.9722842, 1e-5)
    close(cc.loc['origin_conditioned_upper','weighted_pct'], 8.0966876, 1e-5)
    close(cc.loc['exact_origin_lower','weighted_pct'], 5.9880748, 1e-5)
    close(cc.loc['exact_origin_upper','weighted_pct'], 9.0729925, 1e-5)
    close(core_totals['strict_cross_major_weighted_share_pct'], 2.1296, 1e-3)

    print(json.dumps({
        'primary_n': len(primary), 'jobden_n': len(jobden),
        'strict_occ_job_n': int(jobden['STRICT_OCC_JOB_CHANGE'].sum()),
        'strict_cross_n': int(jobden['STRICT_CROSS_MAJOR'].sum()),
        'rates_file': str(OUT_RATES), 'concordance_file': str(OUT_CONCORD),
        'core_file': str(OUT_CORE), 'results_file': str(OUT_RESULTS),
    }, indent=2))

if __name__ == '__main__':
    main()
