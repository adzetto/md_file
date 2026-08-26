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
np.set_printoptions(precision=5, suppress=True, linewidth=200)
from shell_patch_kinematics import shell_patch_kinematics
from bending_matrices import apply_bending_edge_transformation
from ghost import compute_ghost_position
from constraint_penalty import compute_crease_force_and_stiffness, skew

def fd_jac(fun, x0, h=1e-7):
    x0 = np.asarray(x0, float).ravel(); f0 = np.atleast_1d(fun(x0))
    J = np.zeros((f0.size, x0.size))
    for i in range(x0.size):
        hi = h*max(1.0, abs(x0[i])); xp = x0.copy(); xp[i] += hi; xm = x0.copy(); xm[i] -= hi
        J[:, i] = (np.atleast_1d(fun(xp)) - np.atleast_1d(fun(xm)))/(2*hi)
    return J
def rel(a, b): return np.linalg.norm(a-b)/max(np.linalg.norm(a), np.linalg.norm(b), 1e-300)
def asym(K): return np.linalg.norm(K-K.T)/max(np.linalg.norm(K), 1e-300)

BASE = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.],
                 [1., 1., 0.], [-1., 1., 0.], [0.5, -1., 0.]])
Xf = BASE.copy(); Xf[:, :2] += 0.03*np.random.default_rng(1).standard_normal((6, 2))
x0 = Xf + 0.02*np.random.default_rng(6).standard_normal(Xf.shape)
kin = shell_patch_kinematics(Xf, x0-Xf)

print("="*95)
print("D. Edge transformation Y[ghost rows]  vs  exact d(x_ghost)/d(x_real)  (edge k=0: I=0,P=2,F=1)")
print("="*95)

def ghost_free(xflat):
    xr = xflat.reshape(3, 3)
    rI, rP, rF = xr[0], xr[2], xr[1]
    aI = rP-rF; aP = rF-rI
    Nel = np.cross(aP, aI); Nel /= np.linalg.norm(Nel)
    nI = np.cross(Nel, aI); nI /= np.linalg.norm(nI)
    return compute_ghost_position(rI, rP, rF, nI)

Jg = fd_jac(ghost_free, x0[:3].ravel())
_, Y = apply_bending_edge_transformation(np.eye(18), {'edge_bc': ['free', None, None]}, Xf, x0, kin)
print(f"  FREE  edge : rel.err = {rel(Y[9:12, 0:9], Jg):.3e}   -> {'MATCH' if rel(Y[9:12,0:9],Jg)<1e-6 else 'MISMATCH'}")

def ghost_fixed(xflat):
    xr = xflat.reshape(3, 3)
    rI, rF = xr[0], xr[1]
    RI, RP, RF = Xf[0], Xf[2], Xf[1]
    aI0 = RP-RF; aP0 = RF-RI
    Nel0 = np.cross(aP0, aI0); Nel0 /= np.linalg.norm(Nel0)
    nI0 = np.cross(Nel0, aI0); nI0 /= np.linalg.norm(nI0)
    return rI + 2.0*np.dot(nI0, rF-rI)*nI0

Jgf = fd_jac(ghost_fixed, x0[:3].ravel())
_, Yf = apply_bending_edge_transformation(np.eye(18), {'edge_bc': ['fixed', None, None]}, Xf, x0, kin)
print(f"  FIXED edge : rel.err = {rel(Yf[9:12, 0:9], Jgf):.3e}   -> {'MATCH' if rel(Yf[9:12,0:9],Jgf)<1e-6 else 'MISMATCH'}")
print("    d x_ghost/d x_I  exact :\n", Jgf[:, 0:3])
print("    Y block on node I coded:\n", Yf[9:12, 0:3])
print("    d x_ghost/d x_F  exact  (F = local node 2 -> cols 3:6):\n", Jgf[:, 3:6])
print("    Y block on node F coded:\n", Yf[9:12, 3:6], "   <-- coded as ZERO")
print("    (commented-out line in bending_matrices.py:212 would have set  RF = -2 n n^T)")
print("    -2 n n^T =\n", -2*np.outer(*(lambda v: (v, v))(np.cross(np.cross(
      np.cross(Xf[1]-Xf[0], Xf[2]-Xf[0])/np.linalg.norm(np.cross(Xf[1]-Xf[0], Xf[2]-Xf[0])),
      (Xf[2]-Xf[1])/np.linalg.norm(Xf[2]-Xf[1])), np.zeros(3)) if False else
      (np.cross(np.cross(Xf[1]-Xf[0], Xf[2]-Xf[0])/np.linalg.norm(np.cross(Xf[1]-Xf[0], Xf[2]-Xf[0])),
                (Xf[2]-Xf[1])/np.linalg.norm(Xf[2]-Xf[1]))/np.linalg.norm(
       np.cross(np.cross(Xf[1]-Xf[0], Xf[2]-Xf[0])/np.linalg.norm(np.cross(Xf[1]-Xf[0], Xf[2]-Xf[0])),
                (Xf[2]-Xf[1])/np.linalg.norm(Xf[2]-Xf[1])))))))

print()
print("="*95)
print("E. Crease penalty:  F_p vs dW/dx ,  K_p vs dF_p/dx ,  symmetry")
print("="*95)
rng = np.random.default_rng(21)
kappa = 100.0
for label, ang in [('90 deg fold', np.pi/2), ('30 deg fold', np.pi/6), ('5 deg fold', np.radians(5))]:
    # 4-node crease patch: shared edge (X1,X2), flange apex X3, web apex X4
    X1 = np.array([0., 0., 0.]); X2 = np.array([1., 0., 0.])
    X3 = np.array([0.4, 1.0, 0.0])
    X4 = np.array([0.5, np.cos(ang), np.sin(ang)])
    P0 = np.vstack([X1, X2, X3, X4])
    P = P0 + 0.05*rng.standard_normal(P0.shape)

    def theta_of(pf):
        p = pf.reshape(4, 3)
        m1 = np.cross(p[2]-p[0], p[2]-p[1]); m1 /= np.linalg.norm(m1)
        m2 = np.cross(p[3]-p[0], p[3]-p[1]); m2 /= np.linalg.norm(m2)
        return np.dot(m1, m2)
    C0 = theta_of(P0.ravel())            # "initial_angle" cosine convention
    theta0 = np.arccos(np.clip(C0, -1, 1))

    def W(pf):
        return 0.5*kappa*(np.cos(theta0) - theta_of(pf))**2

    F_p, K_p = compute_crease_force_and_stiffness(P, theta0, kappa)
    g = fd_jac(W, P.ravel(), h=1e-6).ravel()
    J = fd_jac(lambda pf: compute_crease_force_and_stiffness(pf.reshape(4, 3), theta0, kappa)[0],
               P.ravel(), h=1e-6)
    print(f"  {label:12s} theta0={np.degrees(theta0):6.2f}deg  "
          f"rel.err(F_p, dW/dx)={rel(F_p, g):.3e}   "
          f"rel.err(K_p, dF_p/dx)={rel(K_p, J):.3e}   asym(K_p)={asym(K_p):.3e}")

print()
print("  --- is the material part exactly  kappa * g g^T ? ---")
X1 = np.array([0., 0., 0.]); X2 = np.array([1., 0., 0.])
X3 = np.array([0.4, 1.0, 0.0]); X4 = np.array([0.5, 0.0, 1.0])
P = np.vstack([X1, X2, X3, X4]) + 0.05*np.random.default_rng(3).standard_normal((4, 3))
theta0 = np.pi/2
F_p, K_p = compute_crease_force_and_stiffness(P, theta0, kappa)
# rebuild the pieces exactly as coded, then the corrected K_mat2
def pieces(P):
    X1, X2, X3, X4 = P
    a1_1 = X3-X1; a2_1 = X3-X2
    m1 = np.cross(a1_1, a2_1); A1 = np.linalg.norm(m1); e1 = m1/A1
    M1_1, M2_1 = skew(a1_1), skew(a2_1); P1 = np.eye(3)-np.outer(e1, e1)
    a1_2 = X4-X1; a2_2 = X4-X2
    m2 = np.cross(a1_2, a2_2); A2 = np.linalg.norm(m2); e2 = m2/A2
    M1_2, M2_2 = skew(a1_2), skew(a2_2); P2 = np.eye(3)-np.outer(e2, e2)
    D1T = np.zeros((12, 3)); D1T[0:3] = M2_1.T; D1T[3:6] = -M1_1.T; D1T[6:9] = M1_1.T-M2_1.T
    D2T = np.zeros((12, 3)); D2T[0:3] = M2_2.T; D2T[3:6] = -M1_2.T; D2T[9:12] = M1_2.T-M2_2.T
    g1 = (1/A1)*D1T@P1.T@e2; g2 = (1/A2)*D2T@P2.T@e1
    return A1, A2, e1, e2, P1, P2, D1T, D2T, g1+g2
A1, A2, e1, e2, P1, P2, D1T, D2T, g = pieces(P)
D1, D2 = D1T.T, D2T.T
Km1 = (1/A1**2)*D1T@P1.T@np.outer(e2, e2)@P1@D1
Km2_coded = (1/(A1*A2))*D2T@P2.T@np.outer(e2, e1)@P1@D1
Km2_fixed = (1/(A1*A2))*D2T@P2.T@np.outer(e1, e2)@P1@D1
Km3 = (1/(A1*A2))*D1T@P1.T@np.outer(e2, e1)@P2@D2
Km4 = (1/A2**2)*D2T@P2.T@np.outer(e1, e1)@P2@D2
Kmat_coded = kappa*(Km1+Km2_coded+Km3+Km4)
Kmat_fixed = kappa*(Km1+Km2_fixed+Km3+Km4)
ggT = kappa*np.outer(g, g)
print(f"    ||K_mat(coded) - kappa g g^T|| / ||kappa g g^T|| = {rel(Kmat_coded, ggT):.3e}")
print(f"    ||K_mat(fixed) - kappa g g^T|| / ||kappa g g^T|| = {rel(Kmat_fixed, ggT):.3e}")
print(f"    asym(K_mat coded) = {asym(Kmat_coded):.3e}    asym(K_mat fixed) = {asym(Kmat_fixed):.3e}")
print(f"    K_mat2(coded) vs K_mat3^T : rel = {rel(Km2_coded, Km3.T):.3e}")
print(f"    K_mat2(fixed) vs K_mat3^T : rel = {rel(Km2_fixed, Km3.T):.3e}")
