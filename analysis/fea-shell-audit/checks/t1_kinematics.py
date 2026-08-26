"""Element-level consistency tests: strains, B-matrices, internal force, tangent."""
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
np.set_printoptions(precision=6, suppress=True, linewidth=150)

from shell_patch_kinematics import shell_patch_kinematics
from membrane_matrices import B_m_matrix, K_m_G_matrix
from bending_matrices import (B_b_matrix, B1_matrix, B2_matrix, H1_matrix,
                              H2_matrix, apply_bending_edge_transformation,
                              K_bending_geometric)
from shell_element import H_matrix, stress_resultants
from shape_functions import shape_function_derivatives

E, nu, t = 2.0e5, 0.35, 6e-4

def make_patch(curved=False, seed=0):
    """6-node patch: primary triangle 1-2-3, neighbours 4 (across edge 2-3),
    5 (across edge 3-1), 6 (across edge 1-2)."""
    X = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [1.0, 1.0, 0.0],   # node 4 : across edge (2,3)
        [-1.0, 1.0, 0.0],  # node 5 : across edge (3,1)
        [0.5, -1.0, 0.0],  # node 6 : across edge (1,2)
    ])
    if curved:                       # lift onto a paraboloid z = k(x^2+y^2)
        k = 0.15
        X[:, 2] = k * (X[:, 0]**2 + X[:, 1]**2)
    rng = np.random.default_rng(seed)
    X = X + 0.02 * rng.standard_normal(X.shape)   # break any accidental symmetry
    return X

def energy_and_force(X_ref, x_curr, Tinv_mode='ref'):
    """Element strain energy and the code's internal force, on an all-internal patch."""
    u_e = x_curr - X_ref
    kin = shell_patch_kinematics(X_ref, u_e)
    A_tri = 0.5*np.sqrt(np.linalg.det(kin['A_cov']))
    H = H_matrix(kin['A_contra'], nu)
    Km = E*t/(1-nu**2); Kb = E*t**3/(12*(1-nu**2))
    m, c = kin['m'], kin['c']
    W = A_tri * (0.5*Km*(m @ H @ m) + 0.5*Kb*(c @ H @ c))

    Tinv = kin['Tinv_ref'] if Tinv_mode == 'ref' else kin['Tinv_curr']
    p, q = stress_resultants(m, c, H, E, nu, t)
    B1 = B1_matrix(Tinv, kin['xi_curr'], kin['eta_curr'], kin['z_curr'])
    H1 = H1_matrix(kin['a1_contra'], kin['a2_contra'], kin['b4'], kin['b5'], kin['b6'])
    H2 = H2_matrix()
    B2 = B2_matrix(kin['a1_cov'], kin['a2_cov'], kin['b4'], kin['b5'], kin['b6'])
    B_b = B_b_matrix(B1, B2, H1, H2, kin['S'], Tinv)
    B_m = B_m_matrix(kin)
    f = A_tri*(B_m.T @ p + B_b.T @ q)
    return W, f, kin, B_m, B_b, p, q, A_tri, H

def fd_jac(fun, x0, h=1e-7):
    x0 = np.asarray(x0, float).ravel()
    f0 = np.atleast_1d(fun(x0))
    J = np.zeros((f0.size, x0.size))
    for i in range(x0.size):
        hi = h*max(1.0, abs(x0[i]))
        xp = x0.copy(); xp[i] += hi
        xm = x0.copy(); xm[i] -= hi
        J[:, i] = (np.atleast_1d(fun(xp)) - np.atleast_1d(fun(xm)))/(2*hi)
    return J

def rel(a, b):
    d = np.linalg.norm(a-b); s = max(np.linalg.norm(a), np.linalg.norm(b), 1e-300)
    return d/s

print("="*78)
print("TEST 1  --  rigid-body motion produces zero strain / zero force")
print("="*78)
for name, curved in [("flat patch", False), ("curved patch", True)]:
    X = make_patch(curved)
    th = 0.7
    Rz = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1.0]])
    th2 = 0.4
    Rx = np.array([[1, 0, 0], [0, np.cos(th2), -np.sin(th2)], [0, np.sin(th2), np.cos(th2)]])
    Rr = Rz @ Rx
    x = (Rr @ X.T).T + np.array([3.0, -2.0, 5.0])
    W, f, kin, *_ = energy_and_force(X, x)
    print(f"  {name:14s}  |m|={np.linalg.norm(kin['m']):.3e}  "
          f"|Eb|={np.linalg.norm(kin['c']):.3e}  W={W:.3e}  |f_int|={np.linalg.norm(f):.3e}")

print()
print("="*78)
print("TEST 2  --  B_m  vs  finite difference of membrane strain m")
print("="*78)
for name, curved in [("flat", False), ("curved", True)]:
    X = make_patch(curved)
    rng = np.random.default_rng(3)
    x0 = X + 0.05*rng.standard_normal(X.shape)
    def m_of(xf):
        xx = xf.reshape(6, 3)
        return shell_patch_kinematics(X, xx - X)['m']
    Bm_fd = fd_jac(m_of, x0.ravel())
    _, _, kin, B_m, *_ = energy_and_force(X, x0)
    print(f"  {name:8s} rel.err(B_m, dm/dx) = {rel(B_m, Bm_fd):.3e}")

print()
print("="*78)
print("TEST 3  --  B_b  vs  finite difference of bending strain Eb = c_ref - c_curr")
print("="*78)
for name, curved in [("flat", False), ("curved", True)]:
    X = make_patch(curved)
    rng = np.random.default_rng(3)
    for amp, lbl in [(0.0, "u = 0        "), (0.05, "u = O(5% h)  "), (0.2, "u = O(20% h) ")]:
        x0 = X + amp*rng.standard_normal(X.shape)
        def c_of(xf):
            xx = xf.reshape(6, 3)
            return shell_patch_kinematics(X, xx - X)['c']
        Bb_fd = fd_jac(c_of, x0.ravel())
        for mode in ('ref', 'curr'):
            _, _, kin, _, B_b, *_ = energy_and_force(X, x0, Tinv_mode=mode)
            print(f"  {name:7s} {lbl} Tinv={mode:4s}  rel.err(B_b, dEb/dx) = {rel(B_b, Bb_fd):.3e}")
    print()

print("="*78)
print("TEST 4  --  f_int  vs  dW/dx   (is the internal force the energy gradient?)")
print("="*78)
for name, curved in [("flat", False), ("curved", True)]:
    X = make_patch(curved)
    rng = np.random.default_rng(11)
    for amp, lbl in [(0.0, "u = 0       "), (0.02, "u small     "), (0.1, "u moderate  ")]:
        x0 = X + amp*rng.standard_normal(X.shape)
        def W_of(xf):
            return energy_and_force(X, xf.reshape(6, 3))[0]
        g_fd = fd_jac(W_of, x0.ravel(), h=1e-6).ravel()
        for mode in ('ref', 'curr'):
            _, f, *_ = energy_and_force(X, x0, Tinv_mode=mode)
            print(f"  {name:7s} {lbl} Tinv={mode:4s}  rel.err(f_int, dW/dx) = {rel(f, g_fd):.3e}")
    print()
