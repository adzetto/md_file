import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC  = _os.path.abspath(_os.environ.get(
    "FEA_SRC", _os.path.join(_HERE, "..", "..", "..", "Fluid_Structure_Program")))
_OUT  = _os.path.abspath(_os.environ.get("FEA_OUT", _os.path.join(_HERE, "_out")))
_os.makedirs(_OUT, exist_ok=True)
if not _os.path.isdir(_SRC):
    _sys.exit("Set FEA_SRC to the directory holding shell_element.py; looked in " + _SRC)

import sys, os, numpy as np
SRC=_SRC
sys.path.insert(0,SRC); sys.path.insert(0,_HERE)
os.chdir(SRC)
from roof_mesh import generate_cylindrical_roof_mesh
from mesh import build_element_topology, build_element_patch_ids, apply_rot_bc
from dof import build_dof_matrix
from ghost import build_ghost_nodes, update_ghost_nodes
from shell_element import shell_element_routine
from opt_element import shell_element_fast
import bending_matrices as BM
from opt_element import K4_fast, K5_fast
E,nu,t=3.10275e3,0.3,12.7
NC0,EC=generate_cylindrical_roof_mesh(2540.,508.,0.1,8,8)
n2i={int(NC0[i,0]):i for i in range(NC0.shape[0])}
Elements,e2i,_=build_element_topology(EC,NC0); apply_rot_bc(Elements,np.zeros((0,3),int))
G,GO=build_ghost_nodes(Elements,NC0,n2i); g2i={g['ID']:i for i,g in enumerate(G)}
for g in G: g['X_ref']=g['X'].copy()
build_element_patch_ids(Elements,GO)
rng=np.random.default_rng(0)
NC=NC0.copy(); NC[:,1:4]+= 8.0*rng.standard_normal((NC0.shape[0],3))   # real deformation
update_ghost_nodes(G,GO,Elements,NC,n2i,g2i,e2i,NC_ref=NC0)
df=dk=0.0; nz=0
for el in Elements:
    f1,K1=shell_element_routine(el,NC0,NC,G,n2i,g2i,E,nu,t,"both")
    f2,K2=shell_element_fast(el,NC0,NC,G,n2i,g2i,E,nu,t,"both")
    df=max(df,np.max(np.abs(f1-f2))/max(np.max(np.abs(f1)),1e-30))
    dk=max(dk,np.max(np.abs(K1-K2))/max(np.max(np.abs(K1)),1e-30))
print(f"DEFORMED mesh, {len(Elements)} elements:")
print(f"  max relative |f_fast - f_orig| = {df:.3e}")
print(f"  max relative |K_fast - K_orig| = {dk:.3e}")
# direct block check with a non-zero force multiplier
a1,a2=rng.standard_normal(3),rng.standard_normal(3)
b4,b5,b6=rng.standard_normal(3),rng.standard_normal(3),rng.standard_normal(3)
v=rng.standard_normal(3)
print(f"  K4 blocks: max|fast-orig| = {np.max(np.abs(K4_fast(a1,a2,v)-BM.K4_geometric_matrix(a1,a2,v))):.3e}")
print(f"  K5 blocks: max|fast-orig| = {np.max(np.abs(K5_fast(a1,a2,b4,b5,b6,v)-BM.K5_geometric_matrix(a1,a2,b4,b5,b6,v))):.3e}"
      f"   (||K5||={np.max(np.abs(BM.K5_geometric_matrix(a1,a2,b4,b5,b6,v))):.3e})")
