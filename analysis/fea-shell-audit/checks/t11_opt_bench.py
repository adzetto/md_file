import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC  = _os.path.abspath(_os.environ.get(
    "FEA_SRC", _os.path.join(_HERE, "..", "..", "..", "Fluid_Structure_Program")))
_OUT  = _os.path.abspath(_os.environ.get("FEA_OUT", _os.path.join(_HERE, "_out")))
_os.makedirs(_OUT, exist_ok=True)
if not _os.path.isdir(_SRC):
    _sys.exit("Set FEA_SRC to the directory holding shell_element.py; looked in " + _SRC)

import sys, os, time, numpy as np
SRC=_SRC
sys.path.insert(0,SRC); sys.path.insert(0,_HERE)
os.chdir(SRC)
from roof_mesh import generate_cylindrical_roof_mesh
from mesh import build_element_topology, build_element_patch_ids, apply_rot_bc
from dof import build_dof_matrix, assemble_K_global
from ghost import build_ghost_nodes
from shell_element import shell_element_routine
from opt_element import shell_element_fast
import scipy.sparse as sp

E,nu,t = 3.10275e3,0.3,12.7
def setup(n):
    NC0,EC=generate_cylindrical_roof_mesh(2540.,508.,0.1,n,n)
    n2i={int(NC0[i,0]):i for i in range(NC0.shape[0])}
    Elements,e2i,_=build_element_topology(EC,NC0); apply_rot_bc(Elements,np.zeros((0,3),int))
    DOF,npr,nfr=build_dof_matrix(NC0,np.array([[1,1,1,1,0.,0.,0.]],float),n2i)
    G,GO=build_ghost_nodes(Elements,NC0,n2i); g2i={g['ID']:i for i,g in enumerate(G)}
    for g in G: g['X_ref']=g['X'].copy()
    build_element_patch_ids(Elements,GO)
    return NC0,Elements,DOF,n2i,npr+nfr,G,g2i

NC0,Elements,DOF,n2i,ndof,G,g2i=setup(16); NC=NC0.copy()
f1,K1=shell_element_routine(Elements[5],NC0,NC,G,n2i,g2i,E,nu,t,"both")
f2,K2=shell_element_fast(Elements[5],NC0,NC,G,n2i,g2i,E,nu,t,"both")
print(f"correctness: max|f_fast-f_orig| = {np.max(np.abs(f1-f2)):.3e}   "
      f"max|K_fast-K_orig| = {np.max(np.abs(K1-K2)):.3e}  (||K||={np.max(np.abs(K1)):.3e})")
print()
print(f"{'nelem':>7s} {'orig f':>9s} {'orig f+K':>10s} {'fast f':>9s} {'fast f+K':>10s} "
      f"{'x(f)':>7s} {'x(f+K)':>8s} {'scatter dense':>14s} {'scatter COO':>12s}")
for n in (16,32,48):
    NC0,Elements,DOF,n2i,ndof,G,g2i=setup(n); NC=NC0.copy()
    def T(fn,mode):
        t0=time.perf_counter()
        for el in Elements: fn(el,NC0,NC,G,n2i,g2i,E,nu,t,mode)
        return time.perf_counter()-t0
    of=T(shell_element_routine,"force"); ok=T(shell_element_routine,"both")
    ff=T(shell_element_fast,"force");    fk=T(shell_element_fast,"both")
    Kes=[shell_element_fast(el,NC0,NC,G,n2i,g2i,E,nu,t,"stiffness")[1] for el in Elements]
    Kd=np.zeros((ndof,ndof))
    t0=time.perf_counter()
    for el,Ke in zip(Elements,Kes): assemble_K_global(Kd,Ke,el['patch_ids'],DOF,n2i)
    ts_dense=time.perf_counter()-t0
    # precomputed COO scatter
    ed=np.array([[ (DOF[n2i[nid],k] if nid in n2i else -1) for nid in el['patch_ids'] for k in range(3)]
                 for el in Elements])
    mask = ed>=0
    rows=np.repeat(ed,18,axis=1).ravel(); cols=np.tile(ed,(1,18)).ravel()
    keep=(rows>=0)&(cols>=0)
    rows,cols=rows[keep],cols[keep]
    data_all=np.array(Kes).reshape(len(Elements),-1).ravel()[keep]
    t0=time.perf_counter()
    Ks=sp.coo_matrix((data_all,(rows,cols)),shape=(ndof,ndof)).tocsr()
    ts_coo=time.perf_counter()-t0
    print(f"{len(Elements):7d} {of:8.3f}s {ok:9.3f}s {ff:8.3f}s {fk:9.3f}s "
          f"{of/ff:6.1f}x {ok/fk:7.1f}x {ts_dense:13.3f}s {ts_coo:11.4f}s")
    print(f"        (scatter check: |dense-sparse| = {abs(Kd-Ks.toarray()).max():.2e})")
