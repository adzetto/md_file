import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC  = _os.path.abspath(_os.environ.get(
    "FEA_SRC", _os.path.join(_HERE, "..", "..", "..", "Fluid_Structure_Program")))
_OUT  = _os.path.abspath(_os.environ.get("FEA_OUT", _os.path.join(_HERE, "_out")))
_os.makedirs(_OUT, exist_ok=True)
if not _os.path.isdir(_SRC):
    _sys.exit("Set FEA_SRC to the directory holding shell_element.py; looked in " + _SRC)

import sys, numpy as np
sys.path.insert(0, _SRC)
np.set_printoptions(precision=4, suppress=True, linewidth=200)
import constraint_penalty as CP
from constraint_penalty import compute_crease_force_and_stiffness, skew

def fd_jac(fun, x0, h=1e-6):
    x0=np.asarray(x0,float).ravel(); f0=np.atleast_1d(fun(x0)); J=np.zeros((f0.size,x0.size))
    for i in range(x0.size):
        hi=h*max(1.,abs(x0[i])); xp=x0.copy(); xp[i]+=hi; xm=x0.copy(); xm[i]-=hi
        J[:,i]=(np.atleast_1d(fun(xp))-np.atleast_1d(fun(xm)))/(2*hi)
    return J
def rel(a,b): return np.linalg.norm(a-b)/max(np.linalg.norm(a),np.linalg.norm(b),1e-300)
def asym(K): return np.linalg.norm(K-K.T)/max(np.linalg.norm(K),1e-300)

kappa=100.0; theta0=np.pi/2
P = np.vstack([[0.,0.,0.],[1.,0.,0.],[0.4,1.,0.],[0.5,0.,1.]]) + 0.05*np.random.default_rng(3).standard_normal((4,3))
F_p, K_p = compute_crease_force_and_stiffness(P, theta0, kappa)
J = fd_jac(lambda pf: compute_crease_force_and_stiffness(pf.reshape(4,3), theta0, kappa)[0], P.ravel())
Jsym = 0.5*(J+J.T)
print(f"exact dF_p/dx symmetric?  asym(FD) = {asym(J):.2e}   (must be ~0 for a conservative penalty)")

# split the coded K_p into K_mat + K_geo by recomputing both halves
X1,X2,X3,X4 = P
a1_1=X3-X1; a2_1=X3-X2; m1=np.cross(a1_1,a2_1); A1=np.linalg.norm(m1); e1=m1/A1
M1_1,M2_1=skew(a1_1),skew(a2_1); P1=np.eye(3)-np.outer(e1,e1)
a1_2=X4-X1; a2_2=X4-X2; m2=np.cross(a1_2,a2_2); A2=np.linalg.norm(m2); e2=m2/A2
M1_2,M2_2=skew(a1_2),skew(a2_2); P2=np.eye(3)-np.outer(e2,e2)
D1T=np.zeros((12,3)); D1T[0:3]=M2_1.T; D1T[3:6]=-M1_1.T; D1T[6:9]=M1_1.T-M2_1.T
D2T=np.zeros((12,3)); D2T[0:3]=M2_2.T; D2T[3:6]=-M1_2.T; D2T[9:12]=M1_2.T-M2_2.T
D1,D2=D1T.T,D2T.T
g=(1/A1)*D1T@P1.T@e2 + (1/A2)*D2T@P2.T@e1
Kmat_fixed = kappa*np.outer(g,g)
Kmat_coded = kappa*((1/A1**2)*D1T@P1.T@np.outer(e2,e2)@P1@D1
                  + (1/(A1*A2))*D2T@P2.T@np.outer(e2,e1)@P1@D1
                  + (1/(A1*A2))*D1T@P1.T@np.outer(e2,e1)@P2@D2
                  + (1/A2**2)*D2T@P2.T@np.outer(e1,e1)@P2@D2)
Kgeo_coded = K_p - Kmat_coded
Kgeo_exact = J - Kmat_fixed     # exact second-derivative part
print()
print(f"K_p as coded          vs exact dF/dx : rel = {rel(K_p, J):.3e}  asym = {asym(K_p):.3e}")
print(f"K_mat2 fix only       vs exact dF/dx : rel = {rel(Kmat_fixed+Kgeo_coded, J):.3e}  "
      f"asym = {asym(Kmat_fixed+Kgeo_coded):.3e}")
print(f"K_mat (fixed) alone   vs exact dF/dx : rel = {rel(Kmat_fixed, J):.3e}")
print()
print(f"geometric part as coded vs exact     : rel = {rel(Kgeo_coded, Kgeo_exact):.3e}  "
      f"asym(coded) = {asym(Kgeo_coded):.3e}  asym(exact) = {asym(Kgeo_exact):.3e}")
print(f"||K_geo coded|| = {np.linalg.norm(Kgeo_coded):.4e}   ||K_geo exact|| = {np.linalg.norm(Kgeo_exact):.4e}")
print()
# how good is dropping the geometric part entirely (a common, legitimate simplification)?
print(f"K_mat(fixed) only, symmetric, positive-semidefinite?  min eig = {np.linalg.eigvalsh(Kmat_fixed).min():.3e}")
print(f"eig range of exact dF/dx (sym part): [{np.linalg.eigvalsh(Jsym).min():.3e}, {np.linalg.eigvalsh(Jsym).max():.3e}]")
