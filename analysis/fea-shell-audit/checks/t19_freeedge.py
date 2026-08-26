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
L=20.
def mesh(n,alt):
    nodes=[];nid=1;nm={}
    for i in range(n+1):
        for j in range(n+1): nodes.append([nid,L*i/n,L*j/n,0.]); nm[(i,j)]=nid; nid+=1
    NC=np.array(nodes);els=[];eid=1
    for i in range(n):
        for j in range(n):
            a,b,c,d=nm[(i,j)],nm[(i+1,j)],nm[(i+1,j+1)],nm[(i,j+1)]
            if alt and (i+j)%2: els.append([eid,a,b,d]);eid+=1;els.append([eid,b,c,d]);eid+=1
            else:               els.append([eid,a,b,c]);eid+=1;els.append([eid,a,c,d]);eid+=1
    return NC,np.array(els,int)
for alt,lbl in ((False,'structured'),(True,'union-jack')):
    NC0,EC=mesh(8,alt)
    n2i={int(NC0[i,0]):i for i in range(NC0.shape[0])}
    with contextlib.redirect_stdout(io.StringIO()):
        Elements,e2i,_=build_element_topology(EC,NC0,angle_tol_deg=5)
        G,GO=build_ghost_nodes(Elements,NC0,n2i)
        for g in G: g['X_ref']=g['X'].copy()
        build_element_patch_ids(Elements,GO)
    g2i={g['ID']:i for i,g in enumerate(G)}
    cnt={0:0,1:0,2:0}; para=[]
    for el in Elements:
        for k in range(3):
            if el['edge_type'][k]=='boundary':
                cnt[k]+=1
                X=get_patch_coordinates(el['patch_ids'],NC0,G,n2i,g2i,NC_ref=NC0,config='reference')
                kin=shell_patch_kinematics(X,np.zeros((6,3)))
                xi=kin['xi_ref'][k]; et=kin['eta_ref'][k]
                para.append((k,round(xi,4),round(et,4)))
    print(f"{lbl:12s} boundary edges by local index k: {cnt}")
    seen=sorted(set(para))
    print(f"             ghost parametric coords (k, xi, eta): {seen}")
    for k,xi,et in seen:
        row=np.array([xi*xi-xi, et*et-et, xi*et])
        print(f"               k={k}: T row = {np.round(row,4)}  ->  kills "
              f"{'c_xixi' if abs(row[0])>1e-9 and abs(row[1])<1e-9 and abs(row[2])<1e-9 else ''}"
              f"{'c_etaeta' if abs(row[1])>1e-9 and abs(row[0])<1e-9 and abs(row[2])<1e-9 else ''}"
              f"{'c_xieta (TWIST)' if abs(row[2])>1e-9 and abs(row[0])<1e-9 and abs(row[1])<1e-9 else ''}")
    print()
