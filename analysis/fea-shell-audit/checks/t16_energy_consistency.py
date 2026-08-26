"""Manufactured-solution energy test.
Impose an exact smooth deflection w(x,y) on every node of a flat plate and compare the
assembled discrete bending energy with the exact Kirchhoff bending energy
   W = D/2 * int [ (w_xx + w_yy)^2 - 2(1-nu)(w_xx w_yy - w_xy^2) ] dA .
No boundary conditions, no solve - purely a question of whether the discrete bending
functional converges to the continuous one."""
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

L, E, nu, t = 20.0, 12.0, 0.0, 1.0
D = E*t**3/(12*(1-nu**2))
A_AMP = 0.02
def w(x, y):  return A_AMP*np.sin(np.pi*x/L)*np.sin(np.pi*y/L)
k = np.pi/L
def wxx(x,y): return -A_AMP*k*k*np.sin(k*x)*np.sin(k*y)
def wyy(x,y): return -A_AMP*k*k*np.sin(k*x)*np.sin(k*y)
def wxy(x,y): return  A_AMP*k*k*np.cos(k*x)*np.cos(k*y)

# exact energy (nu = 0 -> W = D/2 * int (wxx^2 + wyy^2 + 2 wxy^2) dA)
from scipy.integrate import dblquad
Wex,_ = dblquad(lambda yy,xx: wxx(xx,yy)**2 + wyy(xx,yy)**2 + 2*wxy(xx,yy)**2, 0, L, 0, L)
Wex *= D/2

def square_mesh(n, alt=False, lift=False):
    nodes=[];nid=1;nmap={}
    for i in range(n+1):
        for j in range(n+1):
            x,y=L*i/n,L*j/n
            nodes.append([nid,x,y,(w(x,y) if lift else 0.0)]); nmap[(i,j)]=nid; nid+=1
    NC=np.array(nodes);els=[];eid=1
    for i in range(n):
        for j in range(n):
            a,b,c,d=nmap[(i,j)],nmap[(i+1,j)],nmap[(i+1,j+1)],nmap[(i,j+1)]
            if alt and (i+j)%2: els.append([eid,a,b,d]);eid+=1;els.append([eid,b,c,d]);eid+=1
            else:               els.append([eid,a,b,c]);eid+=1;els.append([eid,a,c,d]);eid+=1
    return NC,np.array(els,int)

def discrete_energy(n, alt, interior_only):
    NCf,EC = square_mesh(n,alt,lift=False)
    NCl,_  = square_mesh(n,alt,lift=True)
    n2i={int(NCf[i,0]):i for i in range(NCf.shape[0])}
    with contextlib.redirect_stdout(io.StringIO()):
        Elements,e2i,_=build_element_topology(EC,NCf,angle_tol_deg=5)
        G,GO=build_ghost_nodes(Elements,NCf,n2i)
        for g in G: g['X_ref']=g['X'].copy()
        build_element_patch_ids(Elements,GO)
    g2i={g['ID']:i for i,g in enumerate(G)}
    update_ghost_nodes(G,GO,Elements,NCl,n2i,g2i,e2i,NC_ref=NCf)
    Kb = E*t**3/(12*(1-nu**2))
    W=0.0; Aused=0.0
    for el in Elements:
        if interior_only and any(ty!='internal' for ty in el['edge_type']): continue
        X=get_patch_coordinates(el['patch_ids'],NCf,G,n2i,g2i,NC_ref=NCf,config='reference')
        xc=get_patch_coordinates(el['patch_ids'],NCl,G,n2i,g2i,config='current')
        kin=shell_patch_kinematics(X,xc-X)
        A=0.5*np.sqrt(np.linalg.det(kin['A_cov'])); H=H_matrix(kin['A_contra'],nu)
        c=kin['c']
        W+=A*0.5*Kb*(c@H@c); Aused+=A
    return W, Aused

print(f"exact bending energy over the full plate  W = {Wex:.8e}")
print()
print(f"{'mesh':>14s} {'n':>4s} {'scope':>10s} {'area frac':>10s} {'W_h/W_exact(scaled)':>21s} {'err %':>9s}")
for alt,lbl in ((False,'structured'),(True,'union-jack')):
    for interior_only in (True,False):
        for n in (8,16,24,32,48):
            Wh,Au = discrete_energy(n,alt,interior_only)
            frac = Au/(L*L)
            print(f"{lbl:>14s} {n:4d} {('interior' if interior_only else 'all'):>10s} {frac:10.4f} "
                  f"{Wh/(Wex*frac):21.6f} {100*(Wh/(Wex*frac)-1):9.2f}")
    print()
