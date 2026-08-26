"""System-level check on the real cantilever mesh:
   (a) is the assembled F_int the gradient of the assembled strain energy?
   (b) is the assembled K the Jacobian of F_int?
Measured at a deformed state produced by the code's own solver."""
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
sys.path.insert(0,SRC); os.chdir(SRC)
from mesh import build_element_topology, build_element_patch_ids, apply_rot_bc, get_patch_coordinates
from dof import build_dof_matrix, assemble_F_int, assemble_K_global
from ghost import build_ghost_nodes, update_ghost_nodes
from shell_element import shell_element_routine, H_matrix
from shell_patch_kinematics import shell_patch_kinematics

NC0=np.loadtxt('Cantilever_2e_NC_Sym2.txt',delimiter=','); EC=np.loadtxt('Cantilever_2e_EC_Sym2.txt',delimiter=',').astype(int)
nRN=NC0.shape[0]; n2i={int(NC0[i,0]):i for i in range(nRN)}
E,nu,t,L,P,b = 2e5,0.35,6e-4,0.04,2.25e-5,0.002
disp_bc=np.array([[1,1,1,1,0.,0.,0.],[2,1,1,1,0.,0.,0.],[3,1,1,1,0.,0.,0.]],float)
Elements,e2i,_=build_element_topology(EC,NC0); apply_rot_bc(Elements,np.array([[1,2,1],[2,3,1]],int))
DOF,npr,nfr=build_dof_matrix(NC0,disp_bc,n2i); ndof=npr+nfr
NC_ref=NC0.copy(); NC=NC0.copy()
G,GO=build_ghost_nodes(Elements,NC_ref,n2i); g2i={g['ID']:i for i,g in enumerate(G)}
for g in G: g['X_ref']=g['X'].copy()
build_element_patch_ids(Elements,GO)
free=np.arange(npr,npr+nfr); U=np.zeros(ndof)

def sync():
    for i in range(nRN):
        for a in range(3): NC[i,1+a]=NC_ref[i,1+a]+U[DOF[i,a]]
    update_ghost_nodes(G,GO,Elements,NC,n2i,g2i,e2i,NC_ref=NC_ref)

def Fint():
    F=np.zeros(ndof)
    for el in Elements:
        f,_=shell_element_routine(el,NC_ref,NC,G,n2i,g2i,E,nu,t,compute="force")
        F=assemble_F_int(F,f,el['patch_ids'],DOF,n2i)
    return F
def Kglob():
    K=np.zeros((ndof,ndof))
    for el in Elements:
        _,Ke=shell_element_routine(el,NC_ref,NC,G,n2i,g2i,E,nu,t,compute="stiffness")
        K=assemble_K_global(K,Ke,el['patch_ids'],DOF,n2i)
    return K
def Wtot():
    """Total elastic energy the element's own strain measures imply."""
    W=0.0
    Km=E*t/(1-nu**2); Kb=E*t**3/(12*(1-nu**2))
    for el in Elements:
        Xr=get_patch_coordinates(el['patch_ids'],NC_ref,G,n2i,g2i,NC_ref=NC_ref,config='reference')
        xc=get_patch_coordinates(el['patch_ids'],NC,G,n2i,g2i,config='current')
        kin=shell_patch_kinematics(Xr,xc-Xr)
        A=0.5*np.sqrt(np.linalg.det(kin['A_cov'])); H=H_matrix(kin['A_contra'],nu)
        m,c=kin['m'],kin['c']
        W+=A*(0.5*Km*(m@H@m)+0.5*Kb*(c@H@c))
    return W

# ---- drive to a moderately deformed state with a few Newton steps ----
Fext=np.zeros(ndof)
for nid,fz in [(61,P),(62,2*P),(63,P)]:
    Fext[DOF[n2i[nid],2]]+=fz*0.30           # 30% of full load
sync()
for it in range(40):
    R=(Fext-Fint())[free]
    if np.linalg.norm(R)<1e-9: break
    U[free]+=np.linalg.solve(Kglob()[np.ix_(free,free)],R); sync()
print(f"driven to  ||R||={np.linalg.norm((Fext-Fint())[free]):.3e}  after {it} iters   "
      f"tip w = {NC[n2i[62],3]-NC_ref[n2i[62],3]:.6e} m   w/L={abs(NC[n2i[62],3]-NC_ref[n2i[62],3])/L:.4f}")

# ---- (a) F_int vs dW/dU on the free dofs ----
h=1e-9
g=np.zeros(len(free))
for k,d in enumerate(free):
    hk=h*max(1.0,abs(U[d]))
    U[d]+=hk; sync(); Wp=Wtot()
    U[d]-=2*hk; sync(); Wm=Wtot()
    U[d]+=hk
    g[k]=(Wp-Wm)/(2*hk)
sync()
F=Fint()[free]
print()
print("(a)  assembled internal force  vs  d(total strain energy)/dU")
print(f"     ||F_int||          = {np.linalg.norm(F):.6e}")
print(f"     ||dW/dU||          = {np.linalg.norm(g):.6e}")
print(f"     ||F_int - dW/dU||  = {np.linalg.norm(F-g):.6e}")
print(f"     relative error     = {np.linalg.norm(F-g)/np.linalg.norm(g):.4e}")
print(f"     -> the equilibrium actually solved differs from the variational one by this much")

# ---- (b) K vs dF_int/dU ----
J=np.zeros((len(free),len(free)))
for k,d in enumerate(free):
    hk=1e-9*max(1.0,abs(U[d]))
    U[d]+=hk; sync(); Fp=Fint()[free]
    U[d]-=2*hk; sync(); Fm=Fint()[free]
    U[d]+=hk
    J[:,k]=(Fp-Fm)/(2*hk)
sync()
K=Kglob()[np.ix_(free,free)]
print()
print("(b)  assembled tangent  vs  d(F_int)/dU")
print(f"     rel.err(K, dF/dU) = {np.linalg.norm(K-J)/np.linalg.norm(J):.4e}")
print(f"     asym(K)           = {np.linalg.norm(K-K.T)/np.linalg.norm(K):.4e}")
print(f"     asym(dF/dU)       = {np.linalg.norm(J-J.T)/np.linalg.norm(J):.4e}")
ev=np.linalg.eigvalsh(0.5*(K+K.T))
print(f"     eig(sym K) range  = [{ev.min():.3e}, {ev.max():.3e}]   cond = {ev.max()/max(ev.min(),1e-300):.2e}")

# ---- (c) how big are the two offending quantities on this mesh? ----
dT=[]; zmax=[]
for el in Elements:
    Xr=get_patch_coordinates(el['patch_ids'],NC_ref,G,n2i,g2i,NC_ref=NC_ref,config='reference')
    xc=get_patch_coordinates(el['patch_ids'],NC,G,n2i,g2i,config='current')
    kin=shell_patch_kinematics(Xr,xc-Xr)
    Tr,Tc=kin['Tinv_ref'],kin['Tinv_curr']
    dT.append(np.linalg.norm(Tr-Tc)/np.linalg.norm(Tc))
    h_el=np.sqrt(2*0.5*np.sqrt(np.linalg.det(kin['A_cov'])))
    zmax.append(np.max(np.abs(kin['z_curr']))/h_el)
print()
print("(c)  size of the two modelling errors on this deformed mesh")
print(f"     ||Tinv_ref - Tinv_curr|| / ||Tinv_curr|| :  max {max(dT):.3e}  mean {np.mean(dT):.3e}")
print(f"     |z_i| / element size                     :  max {max(zmax):.3e}  mean {np.mean(zmax):.3e}")
