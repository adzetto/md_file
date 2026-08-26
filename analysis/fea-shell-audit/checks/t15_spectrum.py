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
from mesh import build_element_topology, build_element_patch_ids, build_clamped_rot_bc, apply_rot_bc
from dof import build_dof_matrix, assemble_K_global
from ghost import build_ghost_nodes
from shell_element import shell_element_routine
from traction_load import assemble_traction_force
from bc_setup import build_uniform_traction_bc

def square_mesh(L,n,alt=False):
    nodes=[];nid=1;nmap={}
    for i in range(n+1):
        for j in range(n+1):
            nodes.append([nid,L*i/n,L*j/n,0.0]); nmap[(i,j)]=nid; nid+=1
    NC=np.array(nodes);els=[];eid=1
    for i in range(n):
        for j in range(n):
            a,b,c,d=nmap[(i,j)],nmap[(i+1,j)],nmap[(i+1,j+1)],nmap[(i,j+1)]
            if alt and (i+j)%2: els.append([eid,a,b,d]);eid+=1;els.append([eid,b,c,d]);eid+=1
            else:               els.append([eid,a,b,c]);eid+=1;els.append([eid,a,c,d]);eid+=1
    return NC,np.array(els,int)

L,E,nu,t,q = 20.,12.,0.,1.,-1e-6
for alt,lbl in ((False,'structured'),(True,'union-jack')):
    n=8
    NC0,EC=square_mesh(L,n,alt)
    n2i={int(NC0[i,0]):i for i in range(NC0.shape[0])}
    with contextlib.redirect_stdout(io.StringIO()):
        Elements,e2i,_=build_element_topology(EC,NC0,angle_tol_deg=5)
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
                                  build_uniform_traction_bc(EC,np.array([0.,0.,q])),1.,"constant")
        K=np.zeros((ndof,ndof))
        for el in Elements:
            _,Ke=shell_element_routine(el,NC0,NC,G,n2i,g2i,E,nu,t,"stiffness")
            K=assemble_K_global(K,Ke,el['patch_ids'],DOF,n2i)
    Kff=K[np.ix_(free,free)]
    # separate the transverse (z) dofs
    zsel=[i for i,d in enumerate(free) if any(DOF[k,2]==d for k in range(len(NC0)))]
    ev,V=np.linalg.eigh(0.5*(Kff+Kff.T))
    u=np.linalg.solve(Kff,F[free]); U=np.zeros(ndof); U[free]=u
    ic=np.argmin(np.abs(x-L/2)+np.abs(y-L/2))
    print(f"{lbl:12s} nfree={nfr}  w_c={abs(U[DOF[ic,2]]):.4e}  "
          f"eig min={ev[0]:.4e}  6 smallest={np.array2string(ev[:6],precision=3)}")
    # how much of each low mode is transverse?
    for k in range(4):
        v=V[:,k]; frac=np.linalg.norm(v[zsel])**2
        print(f"      mode {k}: lam={ev[k]:.4e}  transverse energy fraction={frac:.3f}")
    # bending-only vs full: rebuild K with t scaled so membrane is huge (checks membrane locking)
