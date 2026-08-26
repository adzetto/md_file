"""Mesh-sensitivity of the patch curvature estimate: structured vs distorted meshes,
and the conditioning of the 3x3 quadratic-fit matrix T."""
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
from mesh import build_element_topology, build_element_patch_ids, build_clamped_rot_bc, apply_rot_bc, get_patch_coordinates
from dof import build_dof_matrix, assemble_K_global
from ghost import build_ghost_nodes
from shell_element import shell_element_routine
from traction_load import assemble_traction_force
from bc_setup import build_uniform_traction_bc
from shell_patch_kinematics import shell_patch_kinematics

def square_mesh(L,n,distort=0.0,seed=0,alt=False):
    rng=np.random.default_rng(seed)
    nodes=[]; nid=1; nmap={}
    for i in range(n+1):
        for j in range(n+1):
            x,y = L*i/n, L*j/n
            if distort>0 and 0<i<n and 0<j<n:
                x += distort*(L/n)*rng.uniform(-1,1); y += distort*(L/n)*rng.uniform(-1,1)
            nodes.append([nid,x,y,0.0]); nmap[(i,j)]=nid; nid+=1
    NC=np.array(nodes); els=[]; eid=1
    for i in range(n):
        for j in range(n):
            a,b,c,d=nmap[(i,j)],nmap[(i+1,j)],nmap[(i+1,j+1)],nmap[(i,j+1)]
            if alt and (i+j)%2:                     # union-jack style alternation
                els.append([eid,a,b,d]); eid+=1
                els.append([eid,b,c,d]); eid+=1
            else:
                els.append([eid,a,b,c]); eid+=1
                els.append([eid,a,c,d]); eid+=1
    return NC,np.array(els,int)

def run(NC0,EC,clamped,L=20.,E=12.,nu=0.,t=1.,q=-1e-6):
    n2i={int(NC0[i,0]):i for i in range(NC0.shape[0])}
    Elements,e2i,_=build_element_topology(EC,NC0,angle_tol_deg=5)
    if clamped: apply_rot_bc(Elements, build_clamped_rot_bc(Elements))
    x,y=NC0[:,1],NC0[:,2]
    onb=(np.abs(x)<1e-9)|(np.abs(x-L)<1e-9)|(np.abs(y)<1e-9)|(np.abs(y-L)<1e-9)
    disp=np.array([[int(NC0[i,0]),1,1,1,0.,0.,0.] for i in range(len(NC0)) if onb[i]],float)
    DOF,npr,nfr=build_dof_matrix(NC0,disp,n2i); ndof=npr+nfr
    G,GO=build_ghost_nodes(Elements,NC0,n2i); g2i={g['ID']:i for i,g in enumerate(G)}
    for g in G: g['X_ref']=g['X'].copy()
    build_element_patch_ids(Elements,GO)
    NC=NC0.copy(); free=np.arange(npr,npr+nfr)
    F=np.zeros(ndof)
    F=assemble_traction_force(F,Elements,NC0,NC,G,n2i,g2i,DOF,
                              build_uniform_traction_bc(EC,np.array([0.,0.,q])),1.0,"constant")
    K=np.zeros((ndof,ndof)); conds=[]
    for el in Elements:
        _,Ke=shell_element_routine(el,NC0,NC,G,n2i,g2i,E,nu,t,"stiffness")
        K=assemble_K_global(K,Ke,el['patch_ids'],DOF,n2i)
        Xr=get_patch_coordinates(el['patch_ids'],NC0,G,n2i,g2i,NC_ref=NC0,config='reference')
        kin=shell_patch_kinematics(Xr,np.zeros((6,3)))
        conds.append(np.linalg.cond(np.linalg.inv(kin['Tinv_ref'])))
    u=np.linalg.solve(K[np.ix_(free,free)],F[free])
    U=np.zeros(ndof); U[free]=u
    ic=np.argmin(np.abs(x-L/2)+np.abs(y-L/2))
    D=E*t**3/(12*(1-nu**2)); coef=0.00126 if clamped else 0.00406
    return abs(U[DOF[ic,2]]), coef*abs(q)*L**4/D, np.array(conds)

print("Linear square plate, uniform pressure.  'err%' vs Timoshenko closed form.")
print(f"{'BC':>8s} {'mesh':>26s} {'n':>4s} {'err %':>8s} {'cond(T) med':>12s} {'cond(T) max':>12s}")
for clamped,lbl in ((False,'simply'),(True,'clamped')):
    for tag,kw in [('structured right-tri',dict(distort=0.0,alt=False)),
                   ('union-jack alternating',dict(distort=0.0,alt=True)),
                   ('10% node jitter',dict(distort=0.10,alt=False)),
                   ('25% node jitter',dict(distort=0.25,alt=False))]:
        for n in (8,16):
            NC0,EC=square_mesh(20.,n,seed=3,**kw)
            with contextlib.redirect_stdout(io.StringIO()):
                w,wr,cd=run(NC0,EC,clamped)
            print(f"{lbl:>8s} {tag:>26s} {n:4d} {100*(w-wr)/wr:8.2f} "
                  f"{np.median(cd):12.2f} {cd.max():12.2f}")
    print()
