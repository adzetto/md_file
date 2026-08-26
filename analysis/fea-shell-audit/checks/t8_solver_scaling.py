"""Dense vs sparse: what the O(n^2) storage / O(n^3) factorisation actually costs."""
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC  = _os.path.abspath(_os.environ.get(
    "FEA_SRC", _os.path.join(_HERE, "..", "..", "..", "Fluid_Structure_Program")))
_OUT  = _os.path.abspath(_os.environ.get("FEA_OUT", _os.path.join(_HERE, "_out")))
_os.makedirs(_OUT, exist_ok=True)
if not _os.path.isdir(_SRC):
    _sys.exit("Set FEA_SRC to the directory holding shell_element.py; looked in " + _SRC)

import numpy as np, scipy.sparse as sp, scipy.sparse.linalg as spl, time, sys, os
SRC=_SRC
sys.path.insert(0,SRC); os.chdir(SRC)
from roof_mesh import generate_cylindrical_roof_mesh
from mesh import build_element_topology, build_element_patch_ids, apply_rot_bc
from dof import build_dof_matrix
from ghost import build_ghost_nodes

def topo(n):
    NC0,EC = generate_cylindrical_roof_mesh(2540.,508.,0.1,n,n)
    n2i={int(NC0[i,0]):i for i in range(NC0.shape[0])}
    Elements,e2i,_=build_element_topology(EC,NC0); apply_rot_bc(Elements,np.zeros((0,3),int))
    DOF,npr,nfr=build_dof_matrix(NC0,np.array([[1,1,1,1,0.,0.,0.]],float),n2i)
    G,GO=build_ghost_nodes(Elements,NC0,n2i)
    for g in G: g['X_ref']=g['X'].copy()
    build_element_patch_ids(Elements,GO)
    return NC0,Elements,DOF,n2i,npr+nfr,{g['ID']:i for i,g in enumerate(G)}

print(f"{'nx':>4s} {'nelem':>7s} {'ndof':>7s} {'nnz':>9s} {'fill%':>7s} "
      f"{'dense MB':>9s} {'sparse MB':>10s} {'dense LU':>10s} {'sparse LU':>11s} {'speedup':>8s}")
rng=np.random.default_rng(0)
for n in (8,16,24,32,48):
    NC0,Elements,DOF,n2i,ndof,g2i = topo(n)
    rows=[];cols=[]
    for el in Elements:
        ed=[]
        for nid in el['patch_ids']:
            if nid in n2i:
                ed.extend(DOF[n2i[nid],:])
            else: ed.extend([-1,-1,-1])
        ed=[d for d in ed if d>=0]
        for a in ed:
            for bq in ed: rows.append(a); cols.append(bq)
    vals=np.ones(len(rows))
    A=sp.coo_matrix((vals,(rows,cols)),shape=(ndof,ndof)).tocsr()
    A.data[:]=1.0
    nnz=A.nnz
    # build an SPD matrix with that pattern
    Ar=A.copy(); Ar.data = rng.random(nnz)*0.1
    Ar = (Ar+Ar.T)*0.5 + sp.eye(ndof)*ndof
    Ad = Ar.toarray()
    rhs = rng.standard_normal(ndof)
    for _ in range(2): np.linalg.solve(Ad,rhs)          # warm BLAS
    t0=time.perf_counter(); np.linalg.solve(Ad,rhs); td=time.perf_counter()-t0
    Ac=Ar.tocsc()
    spl.splu(Ac)                                         # warm
    t0=time.perf_counter(); lu=spl.splu(Ac); lu.solve(rhs); ts=time.perf_counter()-t0
    print(f"{n:4d} {len(Elements):7d} {ndof:7d} {nnz:9d} {100*nnz/ndof**2:7.3f} "
          f"{ndof*ndof*8/1e6:9.1f} {(nnz*12)/1e6:10.1f} {td:9.4f}s {ts:10.4f}s {td/ts:8.1f}x")

print()
print("extrapolated dense storage:")
for nd in (5000,10000,20000,50000,100000):
    print(f"   ndof={nd:7d}  dense K = {nd*nd*8/1e9:8.2f} GB   sparse (~54 nz/row) = {nd*54*12/1e6:7.1f} MB")
