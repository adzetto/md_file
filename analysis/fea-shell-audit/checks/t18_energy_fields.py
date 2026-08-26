"""Discrete bending energy vs the exact Kirchhoff energy for several smooth fields.
Interior elements only, so the boundary treatment cannot contaminate the answer."""
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
from ghost import build_ghost_nodes, update_ghost_nodes
from shell_patch_kinematics import shell_patch_kinematics
from shell_element import H_matrix
L,E,nu,t = 20.,12.,0.,1.
D=E*t**3/12.; k=np.pi/L
A = 0.02
FIELDS = {
 'x^2  (kxx only)'   : (lambda x,y: A*(x/L)**2,      lambda x,y: (2*A/L**2,0.,0.)),
 'x*y  (pure twist)' : (lambda x,y: A*(x/L)*(y/L),   lambda x,y: (0.,0.,A/L**2)),
 'x^2+y^2 (spheric)' : (lambda x,y: A*((x/L)**2+(y/L)**2), lambda x,y: (2*A/L**2,2*A/L**2,0.)),
 'x^2-y^2 (saddle)'  : (lambda x,y: A*((x/L)**2-(y/L)**2), lambda x,y: (2*A/L**2,-2*A/L**2,0.)),
 'x^3'               : (lambda x,y: A*(x/L)**3,      lambda x,y: (6*A*x/L**3,0.,0.)),
 'x^2 y'             : (lambda x,y: A*(x/L)**2*(y/L),lambda x,y: (2*A*y/L**3,0.,2*A*x/L**3)),
 'sin kx sin ky'     : (lambda x,y: A*np.sin(k*x)*np.sin(k*y),
                        lambda x,y: (-A*k*k*np.sin(k*x)*np.sin(k*y),
                                     -A*k*k*np.sin(k*x)*np.sin(k*y),
                                      A*k*k*np.cos(k*x)*np.cos(k*y))),
 'sin 2kx sin ky'    : (lambda x,y: A*np.sin(2*k*x)*np.sin(k*y),
                        lambda x,y: (-A*4*k*k*np.sin(2*k*x)*np.sin(k*y),
                                     -A*k*k*np.sin(2*k*x)*np.sin(k*y),
                                      A*2*k*k*np.cos(2*k*x)*np.cos(k*y))),
}
def mesh(n,alt,wf):
    nodes=[];nid=1;nm={}
    for i in range(n+1):
        for j in range(n+1):
            x,y=L*i/n,L*j/n; nodes.append([nid,x,y,wf(x,y)]); nm[(i,j)]=nid; nid+=1
    NC=np.array(nodes);els=[];eid=1
    for i in range(n):
        for j in range(n):
            a,b,c,d=nm[(i,j)],nm[(i+1,j)],nm[(i+1,j+1)],nm[(i,j+1)]
            if alt and (i+j)%2: els.append([eid,a,b,d]);eid+=1;els.append([eid,b,c,d]);eid+=1
            else:               els.append([eid,a,b,c]);eid+=1;els.append([eid,a,c,d]);eid+=1
    return NC,np.array(els,int)
def test(n,alt,wf,hessf):
    NCf,EC = mesh(n,alt,lambda x,y:0.0)
    NCl,_  = mesh(n,alt,wf)
    n2i={int(NCf[i,0]):i for i in range(NCf.shape[0])}
    with contextlib.redirect_stdout(io.StringIO()):
        Elements,e2i,_=build_element_topology(EC,NCf,angle_tol_deg=5)
        G,GO=build_ghost_nodes(Elements,NCf,n2i)
        for g in G: g['X_ref']=g['X'].copy()
        build_element_patch_ids(Elements,GO)
    g2i={g['ID']:i for i,g in enumerate(G)}
    update_ghost_nodes(G,GO,Elements,NCl,n2i,g2i,e2i,NC_ref=NCf)
    Kb=E*t**3/(12*(1-nu**2)); Wh=0.; Wex=0.
    for el in Elements:
        if any(ty!='internal' for ty in el['edge_type']): continue
        X=get_patch_coordinates(el['patch_ids'],NCf,G,n2i,g2i,NC_ref=NCf,config='reference')
        xc=get_patch_coordinates(el['patch_ids'],NCl,G,n2i,g2i,config='current')
        kin=shell_patch_kinematics(X,xc-X)
        A=0.5*np.sqrt(np.linalg.det(kin['A_cov'])); H=H_matrix(kin['A_contra'],nu)
        c=kin['c']; Wh += A*0.5*Kb*(c@H@c)
        cen=(X[0]+X[1]+X[2])/3.
        wxx,wyy,wxy=hessf(cen[0],cen[1])
        Wex += A*0.5*D*(wxx**2+wyy**2+2*wxy**2)          # nu = 0
    return Wh,Wex
print("interior-element discrete bending energy / exact  (nu = 0)")
print(f"{'field':>20s} {'n':>4s} {'structured':>12s} {'union-jack':>12s}")
for name,(wf,hf) in FIELDS.items():
    for n in (16,32):
        a,ea=test(n,False,wf,hf); b,eb=test(n,True,wf,hf)
        print(f"{name:>20s} {n:4d} {a/ea:12.5f} {b/eb:12.5f}")
    print()
