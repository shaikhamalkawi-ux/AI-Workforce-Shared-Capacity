from pathlib import Path
from collections import defaultdict, deque
import csv, json, math
import numpy as np
from scipy.optimize import linprog

HERE=Path(__file__).resolve().parent.parent
ROOT=HERE/'data_public'
OUT=HERE/'replay_outputs'
OUT.mkdir(exist_ok=True)
RHOS=[0.25,0.5,0.75,1.0]
TOL=1e-7

def load_vec(path):
    d={}
    with path.open(newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            tc='transfers_k' if 'transfers_k' in r else 'transfer_k'
            d[r['soc']]=(float(r[tc]),float(r['openings_k']))
    return d

def load_origins():
    rows=[]
    with (ROOT/'baseline_positive_any_support_origins.csv').open(newline='',encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    return rows

def load_edges():
    with (ROOT/'frozen_released_top5_edges.csv').open(newline='',encoding='utf-8-sig') as f:
        return sorted({(r['origin_soc'],r['destination_soc']) for r in csv.DictReader(f)})

class Dinic:
    def __init__(self):
        self.g=defaultdict(list)
        self.forward=[]
    def add(self,u,v,c,kind='',key=''):
        a=[v,float(c),None,float(c),kind,key]
        b=[u,0.0,a,0.0,'rev','']
        a[2]=b
        self.g[u].append(a); self.g[v].append(b)
        self.forward.append((u,a))
    def maxflow(self,s,t):
        flow=0.0; INF=1e100
        while True:
            lvl={s:0}; q=deque([s])
            while q:
                u=q.popleft()
                for e in self.g[u]:
                    if e[1]>1e-10 and e[0] not in lvl:
                        lvl[e[0]]=lvl[u]+1; q.append(e[0])
            if t not in lvl: break
            it=defaultdict(int)
            def dfs(u,f):
                if u==t:return f
                while it[u]<len(self.g[u]):
                    e=self.g[u][it[u]]
                    if e[1]>1e-10 and lvl.get(e[0],-1)==lvl[u]+1:
                        z=dfs(e[0],min(f,e[1]))
                        if z>1e-10:
                            e[1]-=z; e[2][1]+=z; return z
                    it[u]+=1
                return 0.0
            while True:
                z=dfs(s,INF)
                if z<=1e-10: break
                flow+=z
        return flow
    def reachable(self,start):
        seen={start}; q=deque([start])
        while q:
            u=q.popleft()
            for e in self.g[u]:
                if e[1]>1e-9 and e[0] not in seen:
                    seen.add(e[0]); q.append(e[0])
        return seen
    def can_reach(self,target):
        pred=defaultdict(list)
        nodes=set(self.g)
        for u,es in self.g.items():
            for e in es:
                if e[1]>1e-9: pred[e[0]].append(u)
        seen={target}; q=deque([target])
        while q:
            v=q.popleft()
            for u in pred.get(v,[]):
                if u not in seen:
                    seen.add(u); q.append(u)
        return seen

def build_flow(vals,origins,edges,rho):
    D=Dinic(); S='S'; Z='T'; supply=sum(vals[o][0] for o in origins)
    INF=max(1,supply)*10
    dests=sorted({d for _,d in edges})
    for o in origins:
        D.add(S,'o:'+o,vals[o][0],'origin_supply',o)
    for o,d in edges:
        D.add('o:'+o,'d:'+d,INF,'route',o+'>'+d)
    for d in dests:
        D.add('d:'+d,Z,rho*vals[d][1],'dest_capacity',d)
    F=D.maxflow(S,Z)
    return D,F,supply,dests

def cut_capacity(D,Sset):
    c=0.0; rows=[]
    for u,e in D.forward:
        v=e[0]; cap=e[3]; kind=e[4]; key=e[5]
        if u in Sset and v not in Sset:
            c+=cap; rows.append((kind,key,u,v,cap))
    return c,rows

def phase3(vals,origins,edges,rho,label):
    D,F,supply,dests=build_flow(vals,origins,edges,rho)
    R=D.reachable('S')
    RT=D.can_reach('T')
    Smin=R
    Smax=set(D.g.keys())-RT
    cmin,rowsmin=cut_capacity(D,Smin); cmax,rowsmax=cut_capacity(D,Smax)
    if abs(cmin-F)>1e-6 or abs(cmax-F)>1e-6:
        raise RuntimeError((label,rho,F,cmin,cmax))
    rows=[]
    for d in dests:
        node='d:'+d
        mandatory=node in Smin
        possible=node in Smax
        rows.append({
            'vintage':label,'rho':rho,'destination_soc':d,
            'capacity_k':rho*vals[d][1],
            'in_every_min_cut':mandatory,
            'in_some_min_cut':possible,
            'in_no_min_cut':not possible,
            'canonical_min_source_side':node in Smin,
            'canonical_max_source_side':node in Smax,
        })
    return {
        'vintage':label,'rho':rho,'max_flow_k':F,'supply_k':supply,
        'mincut_capacity_minSource_k':cmin,'mincut_capacity_maxSource_k':cmax,
        'destination_capacity_arcs_in_every_min_cut':sum(r['in_every_min_cut'] for r in rows),
        'destination_capacity_arcs_in_some_min_cut':sum(r['in_some_min_cut'] for r in rows),
        'destination_capacity_arcs_in_no_min_cut':sum(r['in_no_min_cut'] for r in rows),
        'mandatory_destination_socs':[r['destination_soc'] for r in rows if r['in_every_min_cut']],
        'possible_destination_socs':[r['destination_soc'] for r in rows if r['in_some_min_cut']],
        'canonical_min_cut_origin_supply_arcs':[k for kind,k,*_ in rowsmin if kind=='origin_supply'],
        'canonical_min_cut_destination_capacity_arcs':[k for kind,k,*_ in rowsmin if kind=='dest_capacity'],
        'canonical_max_cut_origin_supply_arcs':[k for kind,k,*_ in rowsmax if kind=='origin_supply'],
        'canonical_max_cut_destination_capacity_arcs':[k for kind,k,*_ in rowsmax if kind=='dest_capacity'],
    },rows

def origin_face(vals,origin_rows,edges,rho,label):
    origins=[r['soc'] for r in origin_rows]
    edge_list=list(edges); n=len(edge_list)
    oe=defaultdict(list); de=defaultdict(list)
    for k,(o,d) in enumerate(edge_list): oe[o].append(k); de[d].append(k)
    dests=sorted(de)
    Aub=[]; bub=[]
    for o in origins:
        inds=oe.get(o,[])
        if inds:
            row=np.zeros(n); row[inds]=1; Aub.append(row); bub.append(vals[o][0])
    for d in dests:
        row=np.zeros(n); row[de[d]]=1; Aub.append(row); bub.append(rho*vals[d][1])
    Aub=np.asarray(Aub); bub=np.asarray(bub)
    res=linprog(-np.ones(n),A_ub=Aub,b_ub=bub,bounds=(0,None),method='highs')
    if not res.success: raise RuntimeError(res.message)
    F=-res.fun
    Aeq=np.ones((1,n)); beq=np.array([F])
    out=[]
    for meta in origin_rows:
        o=meta['soc']; T=vals[o][0]; inds=oe.get(o,[])
        if not inds:
            mn=mx=0.0
        else:
            obj=np.zeros(n); obj[inds]=1
            rmin=linprog(obj,A_ub=Aub,b_ub=bub,A_eq=Aeq,b_eq=beq,bounds=(0,None),method='highs')
            rmax=linprog(-obj,A_ub=Aub,b_ub=bub,A_eq=Aeq,b_eq=beq,bounds=(0,None),method='highs')
            if not (rmin.success and rmax.success): raise RuntimeError((o,rmin.message,rmax.message))
            mn=max(0.0,rmin.fun); mx=max(0.0,-rmax.fun)
        indep=min(T, sum(rho*vals[edge_list[k][1]][1] for k in inds)) if inds else 0.0
        unavoidable_comp=max(0.0, indep-mx)
        max_comp=max(0.0, indep-mn)
        if T<=TOL:
            status='zero_supply'; rmn=rmx=None; cstatus='zero_supply'
        else:
            rmn=mn/T; rmx=mx/T
            if mx<=1e-6: status='never_served'
            elif mn>=T-1e-6: status='necessarily_fully_served'
            elif mx>=T-1e-6: status='possibly_fully_served'
            else: status='unavoidably_underserved'
            if indep<=1e-6:
                cstatus='no_independent_route_capacity'
            elif unavoidable_comp>1e-6:
                cstatus='unavoidably_competition_squeezed'
            elif max_comp>1e-6:
                cstatus='competition_allocation_sensitive'
            else:
                cstatus='competition_neutral'
        out.append({
            'vintage':label,'rho':rho,'origin_soc':o,'title':meta.get('title',''),
            'soc_major':o[:2], 'supply_k':T,'min_optimal_service_k':mn,'max_optimal_service_k':mx,
            'min_service_share': '' if rmn is None else rmn,
            'max_service_share': '' if rmx is None else rmx,
            'independent_ceiling_k':indep,
            'independent_ceiling_share': '' if T<=TOL else indep/T,
            'local_route_shortfall_k':max(0,T-indep),
            'min_unavoidable_shortfall_k':max(0,T-mx),
            'max_possible_shortfall_k':max(0,T-mn),
            'unavoidable_competition_loss_k':unavoidable_comp,
            'max_competition_loss_k':max_comp,
            'competition_status':cstatus,
            'allocation_width_k':mx-mn,
            'status':status,
            'always_positive_service': mn>1e-6,
            'allocation_sensitive': (mx-mn)>1e-6,
        })
    return F,out

def write_csv(path,rows):
    if not rows:return
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)

def summarize_origin(rows):
    pos=[r for r in rows if r['status']!='zero_supply']
    by=defaultdict(int)
    for r in rows: by[r['status']]+=1
    un=[r for r in pos if r['status'] in ('unavoidably_underserved','never_served')]
    total_supply=sum(r['supply_k'] for r in pos)
    unavoidable_k=sum(r['min_unavoidable_shortfall_k'] for r in pos)
    local_k=sum(r['local_route_shortfall_k'] for r in pos)
    unavoid_comp_k=sum(r['unavoidable_competition_loss_k'] for r in pos)
    comp_status=defaultdict(int)
    for r in rows: comp_status[r['competition_status']]+=1
    major=defaultdict(lambda:{'n':0,'supply_k':0.0,'unavoidable_k':0.0,'unavoidable_n':0})
    for r in pos:
        x=major[r['soc_major']]; x['n']+=1; x['supply_k']+=r['supply_k']; x['unavoidable_k']+=r['min_unavoidable_shortfall_k']; x['unavoidable_n']+=r['min_unavoidable_shortfall_k']>1e-6
    major_rows=[]
    for m,x in sorted(major.items()):
        x=dict(x); x['soc_major']=m; x['unavoidable_share_of_major_supply']=x['unavoidable_k']/x['supply_k'] if x['supply_k'] else 0
        major_rows.append(x)
    return {
        'status_counts':dict(by),'positive_supply_origins':len(pos),
        'unavoidably_underserved_count':len(un),'total_supply_k':total_supply,
        'minimum_unavoidable_shortfall_k':unavoidable_k,
        'minimum_unavoidable_shortfall_share':unavoidable_k/total_supply if total_supply else 0,
        'local_route_shortfall_k':local_k,
        'local_route_shortfall_share':local_k/total_supply if total_supply else 0,
        'unavoidable_competition_loss_k':unavoid_comp_k,
        'unavoidable_competition_loss_share':unavoid_comp_k/total_supply if total_supply else 0,
        'competition_status_counts':dict(comp_status),
        'major_group_summary':major_rows,
    }

def main():
    origin_rows=load_origins(); origins=[r['soc'] for r in origin_rows]; edges=load_edges()
    old=load_vec(ROOT/'BLS2024_34_vectors_used.csv'); new=load_vec(ROOT/'BLS2025_35_vectors_used.csv')
    vintages=[('2024-34',old),('2025-35',new)]
    summary={'phase2':{},'phase3':{}}
    all_origin=[]; all_cut=[]
    for label,vals in vintages:
        summary['phase2'][label]={}; summary['phase3'][label]={}
        for rho in RHOS:
            F,orows=origin_face(vals,origin_rows,edges,rho,label)
            all_origin.extend(orows)
            osum=summarize_origin(orows); osum['max_flow_k']=F
            summary['phase2'][label][str(rho)]=osum
            csum,crows=phase3(vals,origins,edges,rho,label)
            all_cut.extend(crows); summary['phase3'][label][str(rho)]=csum
            print(label,rho,'origin statuses',osum['status_counts'],'unavoidable share',osum['minimum_unavoidable_shortfall_share'])
            print(label,rho,'mincut mandatory dest',csum['destination_capacity_arcs_in_every_min_cut'],'possible',csum['destination_capacity_arcs_in_some_min_cut'])
    a=set(summary['phase3']['2024-34']['0.5']['mandatory_destination_socs'])
    b=set(summary['phase3']['2025-35']['0.5']['mandatory_destination_socs'])
    summary['phase3']['primary_rho_temporal_overlap']={'old_n':len(a),'new_n':len(b),'intersection_n':len(a&b),'union_n':len(a|b),'jaccard':len(a&b)/len(a|b) if a|b else 1.0,'old_only':sorted(a-b),'new_only':sorted(b-a),'intersection':sorted(a&b)}
    for label,_ in vintages:
        sets=[set(summary['phase3'][label][str(r)]['mandatory_destination_socs']) for r in RHOS]
        summary['phase3'][label]['rho_invariant_mandatory_destinations']=sorted(set.intersection(*sets) if sets else set())
        summary['phase3'][label]['rho_union_mandatory_destinations']=sorted(set.union(*sets) if sets else set())
    write_csv(OUT/'origin_optimal_face_all_vintages_rho.csv',all_origin)
    write_csv(OUT/'destination_mincut_classification_all_vintages_rho.csv',all_cut)
    (OUT/'phase2_phase3_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    for label,_ in vintages:
        p=[r for r in all_origin if r['vintage']==label and abs(float(r['rho'])-.5)<1e-12]
        write_csv(OUT/f'origin_optimal_face_{label}_rho050.csv',p)
        c=[r for r in all_cut if r['vintage']==label and abs(float(r['rho'])-.5)<1e-12]
        write_csv(OUT/f'destination_mincut_{label}_rho050.csv',c)
    print('OUT',OUT)

if __name__=='__main__': main()
