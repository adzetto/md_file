"""Is K_e the exact Jacobian of f_int_e?  Is it symmetric?"""
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
np.set_printoptions(precision=4, suppress=True, linewidth=220)

import shell_element as SE
from shell_patch_kinematics import shell_patch_kinematics
from membrane_matrices import B_m_matrix, K_m_G_matrix
from bending_matrices import (B_b_matrix, B1_matrix, B2_matrix, H1_matrix,
                              H2_matrix, apply_bending_edge_transformation, K_bending_geometric)
from shape_functions import shape_function_derivatives

E, nu, t = 2.0e5, 0.35, 6e-4

BASE = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.],
                 [1., 1., 0.], [-1., 1., 0.], [0.5, -1., 0.]])

def elem_fk(X_ref, x_curr, edge_bc=(None, None, None), thick=t):
    """Replicates shell_element_routine on a stand-alone patch."""
    elem = {'edge_bc': list(edge_bc)}
    u_e = x_curr - X_ref
    kin = shell_patch_kinematics(X_ref, u_e)
    Tinv = kin['Tinv_ref']; S = kin['S']
    A_tri = 0.5*np.sqrt(np.linalg.det(kin['A_cov']))
    H = SE.H_matrix(kin['A_contra'], nu)
    p, q = SE.stress_resultants(kin['m'], kin['c'], H, E, nu, thick)
    B1 = B1_matrix(Tinv, kin['xi_curr'], kin['eta_curr'], kin['z_curr'])
    H1 = H1_matrix(kin['a1_contra'], kin['a2_contra'], kin['b4'], kin['b5'], kin['b6'])
    H2 = H2_matrix()
    B2 = B2_matrix(kin['a1_cov'], kin['a2_cov'], kin['b4'], kin['b5'], kin['b6'])
    B_b = B_b_matrix(B1, B2, H1, H2, S, Tinv)
    Kbg = K_bending_geometric(Tinv, q, kin['xi_curr'], kin['eta_curr'], kin['z_curr'],
                              B1, B2, H1, H2, kin['a1_cov'], kin['a2_cov'],
                              kin['b4'], kin['b5'], kin['b6'], elem, x_curr)
    Hb = E*thick**3/(12*(1-nu**2))*H
    Bb_mod, Y = apply_bending_edge_transformation(B_b, elem, X_ref, x_curr, kin)
    dN = shape_function_derivatives()
    B_m = B_m_matrix(kin)
    Kmg = K_m_G_matrix(p, dN[:, 0], dN[:, 1])
    f = A_tri*(B_m.T @ p) + A_tri*(Bb_mod.T @ q)
    Hm = E*thick/(1-nu**2)*H
    K_m = (B_m.T @ Hm @ B_m + Kmg)*A_tri
    K_b = (Bb_mod.T @ Hb @ Bb_mod + Y.T @ Kbg @ Y)*A_tri
    return f, K_m + K_b, K_m, K_b, A_tri, B_m, Bb_mod, p, q, Kmg, Y

def fd_jac(fun, x0, h=1e-7):
    x0 = np.asarray(x0, float).ravel(); f0 = np.atleast_1d(fun(x0))
    J = np.zeros((f0.size, x0.size))
    for i in range(x0.size):
        hi = h*max(1.0, abs(x0[i])); xp = x0.copy(); xp[i] += hi; xm = x0.copy(); xm[i] -= hi
        J[:, i] = (np.atleast_1d(fun(xp)) - np.atleast_1d(fun(xm)))/(2*hi)
    return J

def rel(a, b):
    return np.linalg.norm(a-b)/max(np.linalg.norm(a), np.linalg.norm(b), 1e-300)

def asym(K):
    return np.linalg.norm(K-K.T)/max(np.linalg.norm(K), 1e-300)

print("="*100)
print("A.  MEMBRANE block only (thickness huge so bending is negligible is not needed -")
print("    we simply compare K_m against d(f_m)/dx).")
print("="*100)
rng = np.random.default_rng(4)
X = BASE + 0.05*rng.standard_normal(BASE.shape)
for amp in (1e-2, 1e-1):
    x0 = X + amp*rng.standard_normal(X.shape)
    def fm(xf):
        kin = shell_patch_kinematics(X, xf.reshape(6, 3)-X)
        A = 0.5*np.sqrt(np.linalg.det(kin['A_cov']))
        H = SE.H_matrix(kin['A_contra'], nu)
        p, _ = SE.stress_resultants(kin['m'], kin['c'], H, E, nu, t)
        return A*(B_m_matrix(kin).T @ p)
    J = fd_jac(fm, x0.ravel())
    _, _, K_m, *_ = elem_fk(X, x0)
    print(f"  u={amp:6.0e}   rel.err(K_m, d f_m/dx) = {rel(K_m, J):.3e}    asym(K_m)={asym(K_m):.2e}")

print()
print("="*100)
print("B.  BENDING block only:  K_b  vs  d(f_b)/dx     (K_b = Bb^T Hb Bb + Y^T Kbg Y, all * A)")
print("="*100)
for kind, Xp in [('flat', BASE.copy()), ('curved', None)]:
    if Xp is None:
        Xp = BASE.copy(); Xp[:, :2] += 0.05*rng.standard_normal((6, 2))
        Xp[:, 2] = 0.15*(Xp[:, 0]**2 + Xp[:, 1]**2)
    for amp in (1e-3, 1e-2, 1e-1):
        x0 = Xp + amp*np.random.default_rng(9).standard_normal(Xp.shape)
        def fb(xf):
            return elem_fk(Xp, xf.reshape(6, 3))[0] - _fm_only(Xp, xf.reshape(6, 3))
        def _fm_only(Xr, xc):
            kin = shell_patch_kinematics(Xr, xc-Xr)
            A = 0.5*np.sqrt(np.linalg.det(kin['A_cov']))
            H = SE.H_matrix(kin['A_contra'], nu)
            p, _ = SE.stress_resultants(kin['m'], kin['c'], H, E, nu, t)
            return A*(B_m_matrix(kin).T @ p)
        J = fd_jac(fb, x0.ravel(), h=1e-7)
        _, _, _, K_b, *_ = elem_fk(Xp, x0)
        print(f"  {kind:7s} u={amp:6.0e}   rel.err(K_b, d f_b/dx) = {rel(K_b, J):.3e}   asym(K_b)={asym(K_b):.2e}")
    print()

print("="*100)
print("C.  FULL element tangent  K_e  vs  d(f_int)/dx , and symmetry")
print("="*100)
for kind, Xp in [('flat', BASE.copy()), ('curved', None)]:
    if Xp is None:
        Xp = BASE.copy(); Xp[:, :2] += 0.05*np.random.default_rng(2).standard_normal((6, 2))
        Xp[:, 2] = 0.15*(Xp[:, 0]**2 + Xp[:, 1]**2)
    for amp in (1e-3, 1e-2, 1e-1):
        x0 = Xp + amp*np.random.default_rng(9).standard_normal(Xp.shape)
        J = fd_jac(lambda xf: elem_fk(Xp, xf.reshape(6, 3))[0], x0.ravel())
        f, K, *_ = elem_fk(Xp, x0)
        print(f"  {kind:7s} u={amp:6.0e}   rel.err(K_e, d f/dx) = {rel(K, J):.3e}   asym(K_e)={asym(K):.3e}   asym(FD)={asym(J):.3e}")
    print()

print("="*100)
print("D.  Edge transformation Y  vs  exact  d(x_ghost)/d(x_real)")
print("="*100)
from ghost import compute_ghost_position

def ghost_pos(kind, xr):
    """ghost.py's own rule, edge k=0 (I=0,P=2,F=1)."""
    rI, rP, rF = xr[0], xr[2], xr[1]
    if kind == 'free':
        aI = rP-rF; aP = rF-rI
        Nel = np.cross(aP, aI); Nel /= np.linalg.norm(Nel)
        nI = np.cross(Nel, aI); nI /= np.linalg.norm(nI)
        return compute_ghost_position(rI, rP, rF, nI)
    else:                      # 'fixed' -> reference normal, current aP
        return None

Xf = BASE.copy(); Xf[:, :2] += 0.03*np.random.default_rng(1).standard_normal((6, 2))
x0 = Xf + 0.02*np.random.default_rng(6).standard_normal(Xf.shape)
Jg = fd_jac(lambda xf: ghost_pos('free', xf.reshape(6, 3)[:3]), x0[:3].ravel())
kin = shell_patch_kinematics(Xf, x0-Xf)
Bb = np.eye(18)
_, Y = apply_bending_edge_transformation(Bb, {'edge_bc': ['free', None, None]}, Xf, x0, kin)
print("  free edge:  rel.err(Y[ghost rows], d x_ghost/d x_real) =",
      f"{rel(Y[9:12, 0:9], Jg):.3e}")

# fixed edge
def ghost_fixed(xf):
    xr = xf.reshape(6, 3)
    rI, rP, rF = xr[0], xr[2], xr[1]
    RI, RP, RF = Xf[0], Xf[2], Xf[1]
    aI0 = RP-RF; aP0 = RF-RI
    Nel0 = np.cross(aP0, aI0); Nel0 /= np.linalg.norm(Nel0)
    nI0 = np.cross(Nel0, aI0); nI0 /= np.linalg.norm(nI0)
    return rI + 2.0*np.dot(nI0, rF-rI)*nI0
Jgf = fd_jac(ghost_fixed, x0.ravel())[:, :9]
_, Yf = apply_bending_edge_transformation(np.eye(18), {'edge_bc': ['fixed', None, None]}, Xf, x0, kin)
print("  fixed edge: rel.err(Y[ghost rows], d x_ghost/d x_real) =",
      f"{rel(Yf[9:12, 0:9], Jgf):.3e}")
print("     Y block on node I (coded):\n", Yf[9:12, 0:3])
print("     exact d x_ghost/d x_I:\n", Jgf[:, 0:3])
print("     Y block on node F (coded, F = local node 2 -> cols 3:6):\n", Yf[9:12, 3:6])
print("     exact d x_ghost/d x_F:\n", Jgf[:, 3:6])
