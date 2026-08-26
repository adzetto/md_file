"""Cantilever large-deflection benchmark, run as shipped and with each fix applied.
No plotting.  Reports tip deflection vs the reference curve in Book_results_cantilever.txt."""
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC  = _os.path.abspath(_os.environ.get(
    "FEA_SRC", _os.path.join(_HERE, "..", "..", "..", "Fluid_Structure_Program")))
_OUT  = _os.path.abspath(_os.environ.get("FEA_OUT", _os.path.join(_HERE, "_out")))
_os.makedirs(_OUT, exist_ok=True)
if not _os.path.isdir(_SRC):
    _sys.exit("Set FEA_SRC to the directory holding shell_element.py; looked in " + _SRC)

import sys, os, time, numpy as np
SRC = _SRC
sys.path.insert(0, SRC); os.chdir(SRC)

import shell_element as SE
import bending_matrices as BM
from mesh import build_element_topology, build_element_patch_ids, apply_rot_bc
from dof import build_dof_matrix, assemble_F_int, assemble_K_global
from ghost import build_ghost_nodes, update_ghost_nodes
from shell_patch_kinematics import shell_patch_kinematics

VARIANT = sys.argv[1] if len(sys.argv) > 1 else 'as_shipped'

# ---------------- optional patches ----------------
_orig_H1 = BM.H1_matrix
def H1_fixed(a1c, a2c, b4, b5, b6, debug=True):
    raise RuntimeError('needs kin; installed via shell_element patch')

if VARIANT in ('tinv_curr', 'tinv_curr_h1'):
    _src = open(os.path.join(SRC, 'shell_element.py')).read()
    _src = _src.replace("Tinv = kin['Tinv_ref']", "Tinv = kin['Tinv_curr']")
    if VARIANT == 'tinv_curr_h1':
        _src = _src.replace(
            "H1 = H1_matrix(kin['a1_contra'], kin['a2_contra'],\n                   kin['b4'], kin['b5'], kin['b6'])",
            "H1 = _H1_full(kin)")
        _src = _src.replace("import numpy as np", """import numpy as np
def _H1_full(kin):
    a1c, a2c = kin['a1_contra'], kin['a2_contra']
    bb = [kin['b4'], kin['b5'], kin['b6']]; z = kin['z_curr']
    a1, a2 = kin['a1_cov'], kin['a2_cov']
    ncr = np.cross(a1, a2); L = np.linalg.norm(ncr); n = ncr/L
    P = np.eye(3) - np.outer(n, n)
    def cm(v): return np.array([[0,-v[2],v[1]],[v[2],0,-v[0]],[-v[1],v[0],0]])
    M1, M2 = cm(a1), cm(a2)
    H1 = np.zeros((6,18))
    for i in range(3):
        k = np.dot(bb[i], a2c); l = np.dot(bb[i], a1c)
        for ai, ac in enumerate([a1c, a2c]):
            r = 2*i+ai
            H1[r,3:6]   += k*ac + z[i]*((ac @ P @ M1)/L)
            H1[r,6:9]   += -l*ac + z[i]*((ac @ P @ M2)/L)
            H1[r,3*(3+i):3*(3+i)+3] += ac
    return H1
""", 1)
    ns = {}
    exec(compile(_src, 'shell_element_patched.py', 'exec'), ns)
    SE_routine = ns['shell_element_routine']
else:
    SE_routine = SE.shell_element_routine

# ---------------- problem setup (mirrors maindriver_cantilever.py) ----------------
NC0 = np.loadtxt('Cantilever_2e_NC_Sym2.txt', delimiter=',')
EC  = np.loadtxt('Cantilever_2e_EC_Sym2.txt', delimiter=',').astype(int)
numRealNodes = NC0.shape[0]
node_id_to_index = {int(NC0[i,0]): i for i in range(numRealNodes)}
E, nu, t, L, P, b = 2e5, 0.35, 6e-4, 0.04, 0.0000225, 0.002

disp_bc = np.array([[1,1,1,1,0.,0.,0.],[2,1,1,1,0.,0.,0.],[3,1,1,1,0.,0.,0.]], float)
point_load_bc = np.array([[61,0.,0.,P],[62,0.,0.,2*P],[63,0.,0.,P]], float)
tip_node_id = 62
time_steps = np.arange(0.0, 1.0+0.05, 0.05)

Elements, elem_id_to_index_map, _ = build_element_topology(EC, NC0)
apply_rot_bc(Elements, np.array([[1,2,1],[2,3,1]], int))
DOF, nprdof, nfrdof = build_dof_matrix(NC0, disp_bc, node_id_to_index)
ndof = nprdof+nfrdof
U = np.zeros(ndof); U_n = np.zeros(ndof)
NC_ref = NC0.copy(); NC = NC0.copy()
GhostNodes, GhostOrigin = build_ghost_nodes(Elements, NC_ref, node_id_to_index)
ghost_id_to_index = {g['ID']: i for i,g in enumerate(GhostNodes)}
for g in GhostNodes: g['X_ref'] = g['X'].copy()
build_element_patch_ids(Elements, GhostOrigin)
free = np.arange(nprdof, nprdof+nfrdof)

def sync():
    for i in range(numRealNodes):
        for a in range(3):
            NC[i,1+a] = NC_ref[i,1+a] + U[DOF[i,a]]
    update_ghost_nodes(GhostNodes, GhostOrigin, Elements, NC,
                       node_id_to_index, ghost_id_to_index, elem_id_to_index_map, NC_ref=NC_ref)

def internal_force():
    F = np.zeros(ndof)
    for elem in Elements:
        f,_ = SE_routine(elem, NC_ref, NC, GhostNodes, node_id_to_index,
                         ghost_id_to_index, E, nu, t, compute="force")
        F = assemble_F_int(F, f, elem['patch_ids'], DOF, node_id_to_index)
    return F

def stiffness():
    K = np.zeros((ndof, ndof))
    for elem in Elements:
        _,Ke = SE_routine(elem, NC_ref, NC, GhostNodes, node_id_to_index,
                          ghost_id_to_index, E, nu, t, compute="stiffness")
        K = assemble_K_global(K, Ke, elem['patch_ids'], DOF, node_id_to_index)
    return K

rows = []; total_iters = 0; t0 = time.perf_counter()
conv_hist = []
for step, tc in enumerate(time_steps):
    scale = tc/1.0
    U[free] = U_n[free]; sync()
    Fext = np.zeros(ndof)
    for row in point_load_bc:
        idx = node_id_to_index[int(row[0])]
        for a in range(3): Fext[DOF[idx,a]] += row[1+a]*scale
    R = (Fext - internal_force())[free]; nR = np.linalg.norm(R)
    it = 0; hist=[nR]
    while nR > 1e-6 and it < 150:
        it += 1
        K = stiffness()
        du = np.linalg.solve(K[np.ix_(free, free)], R)
        U[free] += du; sync()
        R = (Fext - internal_force())[free]; nR = np.linalg.norm(R); hist.append(nR)
    total_iters += it
    print(f"  step {step:2d} F={2*P*scale*L**2/(E*b*t**3/12):7.3f} iters={it:3d} nR={nR:.2e}", flush=True)
    U_n = U.copy()
    tip = node_id_to_index[tip_node_id]
    w = NC[tip,3]-NC_ref[tip,3]
    I = b*t**3/12.0
    rows.append((abs(w)/L, 2*P*scale*L**2/(E*I), it))
    if step in (1, 10, 20): conv_hist.append((step, hist))
el = time.perf_counter()-t0

print(f"### variant = {VARIANT}")
print(f"    ndof={ndof}  elements={len(Elements)}  ghost={len(GhostNodes)}  "
      f"newton iters total={total_iters}  wall={el:.2f}s")
book = np.loadtxt('Book_results_cantilever.txt', delimiter=',')
print(f"    {'F L^2/EI':>10s} {'z/L (code)':>12s} {'z/L (ref)':>12s} {'diff %':>9s} {'its':>4s}")
for zl, F, it in rows:
    if F <= book[:,1].max() and F > 0:
        ref = np.interp(F, book[:,1], book[:,0])
        print(f"    {F:10.3f} {zl:12.6f} {ref:12.6f} {100*(zl-ref)/ref:9.2f} {it:4d}")
print("    residual history at selected steps:")
for s, h in conv_hist:
    print(f"      step {s:2d}: " + "  ".join(f"{v:.2e}" for v in h[:9]))
np.savetxt(_os.path.join(_OUT, f"cant_{VARIANT}.csv"),
           np.array([[r[0], r[1]] for r in rows]), delimiter=',')
