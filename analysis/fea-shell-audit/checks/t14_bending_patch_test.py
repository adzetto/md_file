"""Bending patch test.  Put every node on an exact quadratic surface
      z = 1/2 (kx x^2 + ky y^2) + kxy x y
so the true curvature is constant.  Each element must reproduce
      c_ab = A_a . Hess(z) . A_b   in its own convected frame.
Any element that does not is inconsistent for bending on that mesh."""
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC  = _os.path.abspath(_os.environ.get(
    "FEA_SRC", _os.path.join(_HERE, "..", "..", "..", "Fluid_Structure_Program")))
_OUT  = _os.path.abspath(_os.environ.get("FEA_OUT", _os.path.join(_HERE, "_out")))
_os.makedirs(_OUT, exist_ok=True)
if not _os.path.isdir(_SRC):
    _sys.exit("Set FEA_SRC to the directory holding shell_element.py; looked in " + _SRC)

import sys, os, io, contextlib, numpy as np
SRC=_SRC
sys.path.insert(0,SRC); os.chdir(SRC)
from mesh import build_element_topology, build_element_patch_ids, get_patch_coordinates
from ghost import build_ghost_nodes
from shell_patch_kinematics import shell_patch_kinematics

KX, KY, KXY = 0.004, -0.002, 0.001
HESS = np.array([[KX, KXY],[KXY, KY]])
def surf(x, y): return 0.5*(KX*x**2 + KY*y**2) + KXY*x*y

def square_mesh(L,n,alt=False,jitter=0.0,seed=1,lift=True):
    rng=np.random.default_rng(seed)
    nodes=[]; nid=1; nmap={}
    for i in range(n+1):
        for j in range(n+1):
            x,y=L*i/n, L*j/n
            if jitter>0 and 0<i<n and 0<j<n:
                x+=jitter*(L/n)*rng.uniform(-1,1); y+=jitter*(L/n)*rng.uniform(-1,1)
            z=surf(x,y) if lift else 0.0
            nodes.append([nid,x,y,z]); nmap[(i,j)]=nid; nid+=1
    NC=np.array(nodes); els=[]; eid=1
    for i in range(n):
        for j in range(n):
            a,b,c,d=nmap[(i,j)],nmap[(i+1,j)],nmap[(i+1,j+1)],nmap[(i,j+1)]
            if alt and (i+j)%2: els.append([eid,a,b,d]); eid+=1; els.append([eid,b,c,d]); eid+=1
            else:               els.append([eid,a,b,c]); eid+=1; els.append([eid,a,c,d]); eid+=1
    return NC,np.array(els,int)

def patch_test(NC0,EC):
    n2i={int(NC0[i,0]):i for i in range(NC0.shape[0])}
    with contextlib.redirect_stdout(io.StringIO()):
        Elements,e2i,_=build_element_topology(EC,NC0,angle_tol_deg=5)
        G,GO=build_ghost_nodes(Elements,NC0,n2i)
        for g in G: g['X_ref']=g['X'].copy()
        build_element_patch_ids(Elements,GO)
    g2i={g['ID']:i for i,g in enumerate(G)}
    errs=[]
    for el in Elements:
        if any(t!='internal' for t in el['edge_type']):   # interior elements only
            continue
        X=get_patch_coordinates(el['patch_ids'],NC0,G,n2i,g2i,NC_ref=NC0,config='reference')
        kin=shell_patch_kinematics(X,np.zeros((6,3)))
        A1,A2=kin['A1_cov'],kin['A2_cov']
        # exact parametric curvature (in-plane projections of the base vectors)
        P1=A1[:2]; P2=A2[:2]
        ex=np.array([P1@HESS@P1, P2@HESS@P2, P1@HESS@P2, P2@HESS@P1])
        # c_ref is the code's curvature of the reference surface
        got=kin['c_ref']
        errs.append(np.linalg.norm(got-ex)/np.linalg.norm(ex))
    return np.array(errs)

print("Reference-configuration curvature of an exactly quadratic surface")
print("(interior elements only; 0 = element reproduces constant curvature exactly)")
print(f"{'mesh':>28s} {'n':>4s} {'#interior':>10s} {'mean rel err':>13s} {'max rel err':>12s}")
for tag,kw in [('structured right-triangle',dict(alt=False)),
               ('union-jack alternating',dict(alt=True)),
               ('right-tri + 10% jitter',dict(alt=False,jitter=0.10)),
               ('right-tri + 25% jitter',dict(alt=False,jitter=0.25))]:
    for n in (8,16,32):
        NC0,EC=square_mesh(20.,n,**kw)
        e=patch_test(NC0,EC)
        print(f"{tag:>28s} {n:4d} {len(e):10d} {e.mean():13.3e} {e.max():12.3e}")
    print()

print("Same test on a flat mesh with a quadratic surface applied only as displacement")
print("(so c_curr, not c_ref, carries the curvature):")
for tag,kw in [('structured right-triangle',dict(alt=False)),('union-jack alternating',dict(alt=True))]:
    for n in (8,16,32):
        NCf,EC=square_mesh(20.,n,lift=False,**kw)
        NCl,_=square_mesh(20.,n,lift=True,**kw)
        n2i={int(NCf[i,0]):i for i in range(NCf.shape[0])}
        with contextlib.redirect_stdout(io.StringIO()):
            Elements,e2i,_=build_element_topology(EC,NCf,angle_tol_deg=5)
            G,GO=build_ghost_nodes(Elements,NCf,n2i)
            for g in G: g['X_ref']=g['X'].copy()
            build_element_patch_ids(Elements,GO)
        g2i={g['ID']:i for i,g in enumerate(G)}
        errs=[]
        for el in Elements:
            if any(t!='internal' for t in el['edge_type']): continue
            X=get_patch_coordinates(el['patch_ids'],NCf,G,n2i,g2i,NC_ref=NCf,config='reference')
            xc=get_patch_coordinates(el['patch_ids'],NCl,G,n2i,g2i,config='current')
            kin=shell_patch_kinematics(X,xc-X)
            A1,A2=kin['A1_cov'],kin['A2_cov']; P1,P2=A1[:2],A2[:2]
            ex=np.array([P1@HESS@P1,P2@HESS@P2,P1@HESS@P2,P2@HESS@P1])
            errs.append(np.linalg.norm(-kin['c']-ex)/np.linalg.norm(ex))   # Eb = c_ref-c_curr = -kappa
        errs=np.array(errs)
        print(f"{tag:>28s} {n:4d} {len(errs):10d} {errs.mean():13.3e} {errs.max():12.3e}")
    print()
