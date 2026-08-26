"""Linear Kirchhoff plate verification: does the element converge to the analytic answer?
Square plate, side L, uniform pressure q, thickness t.  Load kept tiny so the response is linear.
Reference (Timoshenko & Woinowsky-Krieger, Theory of Plates and Shells, 2nd ed., Table 35/8):
   clamped   all round : w_max = 0.00126 q L^4 / D
   simply supported    : w_max = 0.00406 q L^4 / D
"""
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
sys.path.insert(0,SRC); os.chdir(SRC)
from mesh import build_element_topology, build_element_patch_ids, build_clamped_rot_bc, apply_rot_bc
from dof import build_dof_matrix, assemble_F_int, assemble_K_global
from ghost import build_ghost_nodes, update_ghost_nodes
from shell_element import shell_element_routine
from traction_load import assemble_traction_force
from bc_setup import build_uniform_traction_bc

def square_mesh(L, n):
    nodes=[]; nid=1; nmap={}
    for i in range(n+1):
        for j in range(n+1):
            nodes.append([nid, L*i/n, L*j/n, 0.0]); nmap[(i,j)]=nid; nid+=1
    NC=np.array(nodes)
    els=[]; eid=1
    for i in range(n):
        for j in range(n):
            a,b,c,d = nmap[(i,j)], nmap[(i+1,j)], nmap[(i+1,j+1)], nmap[(i,j+1)]
            els.append([eid,a,b,c]); eid+=1
            els.append([eid,a,c,d]); eid+=1
    return NC, np.array(els,int)

def run(n, clamped, L=20.0, E=12.0, nu=0.0, t=1.0, q=-1e-6):
    NC0, EC = square_mesh(L, n)
    n2i={int(NC0[i,0]):i for i in range(NC0.shape[0])}
    Elements,e2i,_ = build_element_topology(EC, NC0, angle_tol_deg=5)
    if clamped:
        apply_rot_bc(Elements, build_clamped_rot_bc(Elements))
    # else: boundary edges keep edge_bc='free' (mirror ghost) -> soft/simply-supported edge
    x,y = NC0[:,1], NC0[:,2]
    onb = (np.abs(x)<1e-9)|(np.abs(x-L)<1e-9)|(np.abs(y)<1e-9)|(np.abs(y-L)<1e-9)
    disp_bc=np.array([[int(NC0[i,0]),1,1,1,0.,0.,0.] for i in range(len(NC0)) if onb[i]],float)
    DOF,npr,nfr = build_dof_matrix(NC0, disp_bc, n2i); ndof=npr+nfr
    G,GO = build_ghost_nodes(Elements, NC0, n2i)
    g2i={g['ID']:i for i,g in enumerate(G)}
    for g in G: g['X_ref']=g['X'].copy()
    build_element_patch_ids(Elements, GO)
    NC=NC0.copy(); free=np.arange(npr,npr+nfr)
    traction_bc = build_uniform_traction_bc(EC, np.array([0.,0.,q]))
    F=np.zeros(ndof)
    F=assemble_traction_force(F,Elements,NC0,NC,G,n2i,g2i,DOF,traction_bc,scale=1.0,load_type="constant")
    K=np.zeros((ndof,ndof))
    for elem in Elements:
        _,Ke = shell_element_routine(elem,NC0,NC,G,n2i,g2i,E,nu,t,compute="stiffness")
        K=assemble_K_global(K,Ke,elem['patch_ids'],DOF,n2i)
    Kff=K[np.ix_(free,free)]
    u=np.linalg.solve(Kff,F[free])
    U=np.zeros(ndof); U[free]=u
    # centre node
    ic=np.argmin(np.abs(x-L/2)+np.abs(y-L/2))
    w=U[DOF[ic,2]]
    D=E*t**3/(12*(1-nu**2))
    coef = 0.00126 if clamped else 0.00406
    w_ref = coef*abs(q)*L**4/D
    return len(Elements), abs(w), w_ref, 100*(abs(w)-w_ref)/w_ref, np.linalg.norm(Kff-Kff.T)/np.linalg.norm(Kff)

import io, contextlib
for clamped in (True, False):
    print("="*88)
    print(("CLAMPED" if clamped else "SIMPLY SUPPORTED (edge_bc='free' mirror ghost, u=v=w=0 on edge)")
          + "  square plate, uniform pressure, LINEAR solve")
    print("="*88)
    print(f"  {'n/side':>7s} {'nelem':>7s} {'w_max FE':>14s} {'w_max exact':>14s} {'err %':>9s} {'asym(K)':>10s}")
    for n in (4, 8, 12, 16, 24):
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf):
            ne,w,wr,err,asy = run(n, clamped)
        print(f"  {n:7d} {ne:7d} {w:14.6e} {wr:14.6e} {err:9.2f} {asy:10.2e}")
    print()
