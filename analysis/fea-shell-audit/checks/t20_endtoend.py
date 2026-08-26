"""One Newton iteration, 4608-element roof (ndof = 7203): where the time goes,
and what each change buys.  All numbers measured on this machine, single process."""
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC  = _os.path.abspath(_os.environ.get(
    "FEA_SRC", _os.path.join(_HERE, "..", "..", "..", "Fluid_Structure_Program")))
_OUT  = _os.path.abspath(_os.environ.get("FEA_OUT", _os.path.join(_HERE, "_out")))
_os.makedirs(_OUT, exist_ok=True)
if not _os.path.isdir(_SRC):
    _sys.exit("Set FEA_SRC to the directory holding shell_element.py; looked in " + _SRC)

import sys, os, time, numpy as np, scipy.sparse as sp, scipy.sparse.linalg as spl
SRC=_SRC
sys.path.insert(0,SRC); sys.path.insert(0,_HERE)
os.chdir(SRC)
import jax, jax.numpy as jnp
from roof_mesh import generate_cylindrical_roof_mesh
from mesh import build_element_topology, build_element_patch_ids, apply_rot_bc, get_patch_coordinates
from dof import build_dof_matrix, assemble_K_global, assemble_F_int
from ghost import build_ghost_nodes
from shell_element import shell_element_routine
from opt_element import shell_element_fast
from jax_element import batch_fk
E,nu,t=3.10275e3,0.3,12.7
n=48
NC0,EC=generate_cylindrical_roof_mesh(2540.,508.,0.1,n,n)
n2i={int(NC0[i,0]):i for i in range(NC0.shape[0])}
Elements,e2i,_=build_element_topology(EC,NC0); apply_rot_bc(Elements,np.zeros((0,3),int))
DOF,npr,nfr=build_dof_matrix(NC0,np.array([[1,1,1,1,0.,0.,0.]],float),n2i); ndof=npr+nfr
G,GO=build_ghost_nodes(Elements,NC0,n2i); g2i={g['ID']:i for i,g in enumerate(G)}
for g in G: g['X_ref']=g['X'].copy()
build_element_patch_ids(Elements,GO)
NC=NC0.copy(); ne=len(Elements)
print(f"mesh: {ne} elements, ndof = {ndof}\n")
def T(f,r=1):
    f(); t0=time.perf_counter()
    for _ in range(r): f()
    return (time.perf_counter()-t0)/r

# --- A. as shipped ---
def A_force():
    F=np.zeros(ndof)
    for el in Elements:
        f,_=shell_element_routine(el,NC0,NC,G,n2i,g2i,E,nu,t,"both")
        F=assemble_F_int(F,f,el['patch_ids'],DOF,n2i)
def A_stiff():
    K=np.zeros((ndof,ndof))
    for el in Elements:
        _,Ke=shell_element_routine(el,NC0,NC,G,n2i,g2i,E,nu,t,"both")
        K=assemble_K_global(K,Ke,el['patch_ids'],DOF,n2i)
    return K
tA_f=T(A_force); K=A_stiff(); tA_k=T(A_stiff)
K=K+np.eye(ndof)*1e6; rhs=np.random.default_rng(0).standard_normal(ndof)
np.linalg.solve(K,rhs); tA_s=T(lambda: np.linalg.solve(K,rhs))
print(f"A  as shipped      : residual asm {tA_f:7.2f}s | tangent asm+scatter {tA_k:7.2f}s | "
      f"dense LU {tA_s:6.2f}s | total {tA_f+tA_k+tA_s:7.2f}s | K mem {ndof*ndof*8/1e6:.0f} MB")

# --- B. quick wins: skip Kbg for force, drop np.block, COO scatter, sparse LU ---
ed=np.array([[(DOF[n2i[nid],k] if nid in n2i else -1) for nid in el['patch_ids'] for k in range(3)]
             for el in Elements])
rows=np.repeat(ed,18,axis=1).ravel(); cols=np.tile(ed,(1,18)).ravel()
keep=(rows>=0)&(cols>=0); rows,cols=rows[keep],cols[keep]
def B_force():
    for el in Elements: shell_element_fast(el,NC0,NC,G,n2i,g2i,E,nu,t,"force")
def B_stiff():
    Ke=np.empty((ne,18,18))
    for i,el in enumerate(Elements):
        Ke[i]=shell_element_fast(el,NC0,NC,G,n2i,g2i,E,nu,t,"stiffness")[1]
    return sp.coo_matrix((Ke.reshape(-1)[keep],(rows,cols)),shape=(ndof,ndof)).tocsc()
tB_f=T(B_force); Ks=B_stiff(); tB_k=T(B_stiff)
Ks=Ks+sp.eye(ndof)*1e6; spl.splu(Ks); tB_s=T(lambda: spl.splu(Ks).solve(rhs))
print(f"B  quick wins      : residual asm {tB_f:7.2f}s | tangent asm+scatter {tB_k:7.2f}s | "
      f"sparse LU {tB_s:6.2f}s | total {tB_f+tB_k+tB_s:7.2f}s | K mem {Ks.data.nbytes*1.5/1e6:.0f} MB")

# --- C. JAX energy + autodiff, vmapped, COO scatter, sparse LU ---
Xs=jnp.array([get_patch_coordinates(el['patch_ids'],NC0,G,n2i,g2i,NC_ref=NC0,config='reference').ravel()
              for el in Elements])
xs=jnp.array([get_patch_coordinates(el['patch_ids'],NC,G,n2i,g2i,config='current').ravel()
              for el in Elements])
r=batch_fk(xs,Xs,E,nu,t); r[0].block_until_ready(); r[1].block_until_ready()
def C_both():
    f,Kj=batch_fk(xs,Xs,E,nu,t); f.block_until_ready(); Kj.block_until_ready(); return f,Kj
tC_e=T(C_both,3)
f,Kj=C_both(); Kn=np.asarray(Kj)
def C_scatter(): return sp.coo_matrix((Kn.reshape(-1)[keep],(rows,cols)),shape=(ndof,ndof)).tocsc()
tC_sc=T(C_scatter)
print(f"C  JAX + sparse    : element f AND K {tC_e:7.2f}s | COO scatter {tC_sc:7.2f}s | "
      f"sparse LU {tB_s:6.2f}s | total {tC_e+tC_sc+tB_s:7.2f}s")
print()
print(f"speedup on one full Newton iteration:  B/A = {(tA_f+tA_k+tA_s)/(tB_f+tB_k+tB_s):.1f}x   "
      f"C/A = {(tA_f+tA_k+tA_s)/(tC_e+tC_sc+tB_s):.1f}x")
