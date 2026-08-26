"""Where does the time actually go, per element and per assembly?"""
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC  = _os.path.abspath(_os.environ.get(
    "FEA_SRC", _os.path.join(_HERE, "..", "..", "..", "Fluid_Structure_Program")))
_OUT  = _os.path.abspath(_os.environ.get("FEA_OUT", _os.path.join(_HERE, "_out")))
_os.makedirs(_OUT, exist_ok=True)
if not _os.path.isdir(_SRC):
    _sys.exit("Set FEA_SRC to the directory holding shell_element.py; looked in " + _SRC)

import sys, os, time, cProfile, pstats, io, numpy as np
SRC=_SRC
sys.path.insert(0,SRC); os.chdir(SRC)
from mesh import build_element_topology, build_element_patch_ids, apply_rot_bc
from dof import build_dof_matrix, assemble_F_int, assemble_K_global
from ghost import build_ghost_nodes, update_ghost_nodes
from shell_element import shell_element_routine
from roof_mesh import generate_cylindrical_roof_mesh

def setup(nx, nphi):
    NC0, EC = generate_cylindrical_roof_mesh(2540.,508.,0.1,nx,nphi)
    n2i = {int(NC0[i,0]):i for i in range(NC0.shape[0])}
    Elements, e2i, _ = build_element_topology(EC, NC0)
    apply_rot_bc(Elements, np.zeros((0,3),int))
    disp = np.array([[int(NC0[0,0]),1,1,1,0.,0.,0.]],float)
    DOF,npr,nfr = build_dof_matrix(NC0, disp, n2i)
    G,GO = build_ghost_nodes(Elements, NC0, n2i)
    g2i = {g['ID']:i for i,g in enumerate(G)}
    for g in G: g['X_ref']=g['X'].copy()
    build_element_patch_ids(Elements, GO)
    return NC0, EC, Elements, e2i, n2i, DOF, npr+nfr, G, g2i

E,nu,t = 3.10275e3, 0.3, 12.7
print(f"{'nx=nphi':>8s} {'nelem':>7s} {'ndof':>7s} {'force asm':>11s} {'stiff asm':>11s} "
      f"{'scatter':>10s} {'dense solve':>12s} {'K mem MB':>10s}")
rows=[]
for n in (8, 16, 24, 32):
    NC0,EC,Elements,e2i,n2i,DOF,ndof,G,g2i = setup(n,n)
    NC = NC0.copy()
    # warm
    shell_element_routine(Elements[0],NC0,NC,G,n2i,g2i,E,nu,t,compute="both")
    t0=time.perf_counter()
    for elem in Elements:
        shell_element_routine(elem,NC0,NC,G,n2i,g2i,E,nu,t,compute="force")
    t_f=time.perf_counter()-t0
    t0=time.perf_counter()
    Kes=[]
    for elem in Elements:
        _,Ke = shell_element_routine(elem,NC0,NC,G,n2i,g2i,E,nu,t,compute="stiffness")
        Kes.append(Ke)
    t_k=time.perf_counter()-t0
    K=np.zeros((ndof,ndof))
    t0=time.perf_counter()
    for elem,Ke in zip(Elements,Kes):
        assemble_K_global(K,Ke,elem['patch_ids'],DOF,n2i)
    t_s=time.perf_counter()-t0
    K += np.eye(ndof)*1e3
    rhs=np.random.default_rng(0).standard_normal(ndof)
    t0=time.perf_counter(); np.linalg.solve(K,rhs); t_sol=time.perf_counter()-t0
    mem = ndof*ndof*8/1e6
    print(f"{n:8d} {len(Elements):7d} {ndof:7d} {t_f:10.3f}s {t_k:10.3f}s {t_s:9.3f}s {t_sol:11.3f}s {mem:10.1f}")
    rows.append((n,len(Elements),ndof,t_f,t_k,t_s,t_sol,mem))

print()
print("per-element cost (ms):")
for n,ne,nd,tf,tk,ts,tsol,mem in rows:
    print(f"  nx={n:3d}  force {1000*tf/ne:7.3f} ms/elem   stiffness {1000*tk/ne:7.3f} ms/elem   "
          f"scatter {1000*ts/ne:7.3f} ms/elem")

print()
print("="*80)
print("cProfile of one stiffness assembly (nx=nphi=16)")
print("="*80)
NC0,EC,Elements,e2i,n2i,DOF,ndof,G,g2i = setup(16,16)
NC=NC0.copy()
pr=cProfile.Profile(); pr.enable()
for elem in Elements:
    shell_element_routine(elem,NC0,NC,G,n2i,g2i,E,nu,t,compute="both")
pr.disable()
s=io.StringIO(); pstats.Stats(pr,stream=s).sort_stats('cumulative').print_stats(22)
print(s.getvalue())
