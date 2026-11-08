"""Проверка оптимальных цен из блока «Бизнес и аналитика» полным перебором целых q (python3 check_optimum.py)."""
import itertools
# demand: q = a - b p ; cost per pax c
M = {'PM':(200,20,1),'MP':(160,20,1),'MS':(120,20,1),'SM':(100,20,1),'PS':(100,10,2),'SP':(80,10,2)}
legs = {'PM':['PM','PS'],'MS':['MS','PS'],'SM':['SM','SP'],'MP':['MP','SP']}
def solve(M, f, comp=0, pi=0.0, cap=150):
    # brute force over integer q (fine enough), check constraints
    best=None
    rng = {k:range(0, a+1) for k,(a,b,c) in M.items()}
    # separable except through PM/MS legs (PS) and SM/MP legs (SP): search PS,SP then optimize others given caps
    def opt_single(k, capleft):
        a,b,c = M[k]; bestv=None
        for q in range(0, min(a, capleft)+1):
            p=(a-q)/b
            v=(1-pi)*(p-c)*q - pi*comp*q
            if bestv is None or v>bestv[0]: bestv=(v,q,p)
        return bestv
    for qps in range(0, M['PS'][0]+1):
        if qps>cap*min(f['PM'],f['MS']): break
        for qsp in range(0, M['SP'][0]+1):
            if qsp>cap*min(f['SM'],f['MP']): break
            tot=0; sol={}
            for k,q in (('PS',qps),('SP',qsp)):
                a,b,c=M[k]; p=(a-q)/b; v=(1-pi)*(p-c)*q-pi*comp*q; tot+=v; sol[k]=(q,p)
            for k,other in (('PM',qps),('MS',qps),('SM',qsp),('MP',qsp)):
                v,q,p = opt_single(k, cap*f[k]-other); tot+=v; sol[k]=(q,p)
            # regulatory
            if sol['PS'][0]>0 and sol['PS'][1] > sol['PM'][1]+sol['MS'][1]+1e-9: continue
            if sol['SP'][0]>0 and sol['SP'][1] > sol['SM'][1]+sol['MP'][1]+1e-9: continue
            tot -= (1-pi)*100*sum(f.values())
            if best is None or tot>best[0]: best=(tot,sol)
    return best
f1={'PM':1,'MS':1,'SM':1,'MP':1}
print('normal', solve(M,f1))
Mp=dict(M); Mp['PM']=(360,20,1)
print('peak', solve(Mp,f1))
print('peak cap151', solve(Mp,f1,cap=151)[0])
print('normal cap151', solve(M,f1,cap=151)[0])
f2={'PM':2,'MS':0,'SM':0,'MP':2}
print('peak route2', solve(Mp,f2))
print('snow', solve(M,f1,comp=4,pi=0.2))
