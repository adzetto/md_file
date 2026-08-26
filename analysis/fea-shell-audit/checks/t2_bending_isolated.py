"""Isolate the bending operator: B_b, bending internal force, bending tangent."""
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
from bending_matrices import (B_b_matrix, B1_matrix, B2_matrix, H1_matrix,
                              H2_matrix, K_bending_geometric)
from shell_element import H_matrix, stress_resultants

E, nu, t = 2.0e5, 0.35, 6e-4
Kb = E*t**3/(12*(1-nu**2))

BASE = np.array([
    [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
    [1.0, 1.0, 0.0], [-1.0, 1.0, 0.0], [0.5, -1.0, 0.0]])

def patch(kind, seed=0):
    X = BASE.copy()
    rng = np.random.default_rng(seed)
    if kind == 'exactly_flat':
        pass
    elif kind == 'flat_jittered_inplane':      # flat but irregular in x-y
        X[:, :2] += 0.05*rng.standard_normal((6, 2))
    elif kind == 'curved':
        X[:, :2] += 0.05*rng.standard_normal((6, 2))
        X[:, 2] = 0.15*(X[:, 0]**2 + X[:, 1]**2)
    return X

def Bb_of(X_ref, x_curr, mode):
    kin = shell_patch_kinematics(X_ref, x_curr - X_ref)
    Tinv = kin['Tinv_ref'] if mode == 'ref' else kin['Tinv_curr']
    B1 = B1_matrix(Tinv, kin['xi_curr'], kin['eta_curr'], kin['z_curr'])
    H1 = H1_matrix(kin['a1_contra'], kin['a2_contra'], kin['b4'], kin['b5'], kin['b6'])
    H2 = H2_matrix()
    B2 = B2_matrix(kin['a1_cov'], kin['a2_cov'], kin['b4'], kin['b5'], kin['b6'])
    return B_b_matrix(B1, B2, H1, H2, kin['S'], Tinv), kin

def fd_jac(fun, x0, h=1e-7):
    x0 = np.asarray(x0, float).ravel(); f0 = np.atleast_1d(fun(x0))
    J = np.zeros((f0.size, x0.size))
    for i in range(x0.size):
        hi = h*max(1.0, abs(x0[i])); xp = x0.copy(); xp[i] += hi; xm = x0.copy(); xm[i] -= hi
        J[:, i] = (np.atleast_1d(fun(xp)) - np.atleast_1d(fun(xm)))/(2*hi)
    return J

def rel(a, b):
    return np.linalg.norm(a-b)/max(np.linalg.norm(a), np.linalg.norm(b), 1e-300)

print("="*90)
print("A.  B_b   vs   exact  d(Eb)/dx    [Eb = c_ref - c_curr, as coded]")
print("="*90)
print(f"{'patch':24s} {'u':10s} {'Tinv=ref':>12s} {'Tinv=curr':>12s}")
for kind in ['exactly_flat', 'flat_jittered_inplane', 'curved']:
    X = patch(kind)
    rng = np.random.default_rng(7)
    for amp, lbl in [(0.0, 'zero'), (1e-3, '1e-3'), (1e-2, '1e-2'), (1e-1, '1e-1')]:
        x0 = X + amp*rng.standard_normal(X.shape)
        Jfd = fd_jac(lambda xf: shell_patch_kinematics(X, xf.reshape(6, 3)-X)['c'], x0.ravel())
        e_ref = rel(Bb_of(X, x0, 'ref')[0], Jfd)
        e_cur = rel(Bb_of(X, x0, 'curr')[0], Jfd)
        print(f"{kind:24s} {lbl:10s} {e_ref:12.3e} {e_cur:12.3e}")
    print()

print("="*90)
print("B.  Is the residual error explained by the term  -z_i (a^alpha . dn)  missing in H1?")
print("     (patched H1 adds that term; measured on the CURRENT-Tinv variant, u=0)")
print("="*90)

def H1_patched(kin):
    """H1 with the missing  -z_i (a^alpha . dn)  contribution restored."""
    a1c, a2c = kin['a1_contra'], kin['a2_contra']
    b = [kin['b4'], kin['b5'], kin['b6']]
    z = kin['z_curr']
    a1, a2 = kin['a1_cov'], kin['a2_cov']
    ncr = np.cross(a1, a2); L = np.linalg.norm(ncr); n = ncr/L
    P = np.eye(3) - np.outer(n, n)
    def cm(v): return np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    M1, M2 = cm(a1), cm(a2)
    H1 = np.zeros((6, 18))
    for i in range(3):
        k = np.dot(b[i], a2c); l = np.dot(b[i], a1c)
        for ai, ac in enumerate([a1c, a2c]):
            r = 2*i + ai
            H1[r, 3*1:3*1+3] += k*ac          # d b2
            H1[r, 3*2:3*2+3] += -l*ac         # d b3
            H1[r, 3*(3+i):3*(3+i)+3] += ac    # d b_{4+i}
            # missing piece:  -z_i * (a^alpha . dn),  dn = (1/L) P (-M2 db3 - M1 db2)
            H1[r, 3*1:3*1+3] += -z[i]*(-(ac @ P @ M1)/L)
            H1[r, 3*2:3*2+3] += -z[i]*(-(ac @ P @ M2)/L)
    return H1

from bending_matrices import B1_matrix as _B1, B2_matrix as _B2, H2_matrix as _H2
for kind in ['exactly_flat', 'flat_jittered_inplane', 'curved']:
    X = patch(kind)
    rng = np.random.default_rng(7)
    for amp, lbl in [(0.0, 'zero'), (1e-2, '1e-2'), (1e-1, '1e-1')]:
        x0 = X + amp*rng.standard_normal(X.shape)
        Jfd = fd_jac(lambda xf: shell_patch_kinematics(X, xf.reshape(6, 3)-X)['c'], x0.ravel())
        kin = shell_patch_kinematics(X, x0-X)
        Tinv = kin['Tinv_curr']
        B1 = _B1(Tinv, kin['xi_curr'], kin['eta_curr'], kin['z_curr'])
        B2 = _B2(kin['a1_cov'], kin['a2_cov'], kin['b4'], kin['b5'], kin['b6'])
        H2 = _H2()
        Bb_fix = B_b_matrix(B1, B2, H1_patched(kin), H2, kin['S'], Tinv)
        Bb_as_coded = Bb_of(X, x0, 'curr')[0]
        print(f"{kind:24s} u={lbl:6s}  as-coded {rel(Bb_as_coded, Jfd):9.3e}   "
              f"H1 term restored {rel(Bb_fix, Jfd):9.3e}   max|z_i|={np.max(np.abs(kin['z_curr'])):.3e}")
    print()

print("="*90)
print("C.  Bending-only internal force  f_b = A * B_b^T q   vs   dW_bend/dx")
print("="*90)
def Wb(X, xf):
    kin = shell_patch_kinematics(X, xf.reshape(6, 3)-X)
    A = 0.5*np.sqrt(np.linalg.det(kin['A_cov']))
    H = H_matrix(kin['A_contra'], nu); c = kin['c']
    return A*0.5*Kb*(c @ H @ c)

for kind in ['exactly_flat', 'flat_jittered_inplane', 'curved']:
    X = patch(kind)
    rng = np.random.default_rng(5)
    for amp, lbl in [(1e-2, '1e-2'), (1e-1, '1e-1')]:
        x0 = X + amp*rng.standard_normal(X.shape)
        g = fd_jac(lambda xf: Wb(X, xf), x0.ravel(), h=1e-6).ravel()
        for mode in ('ref', 'curr'):
            Bb, kin = Bb_of(X, x0, mode)
            A = 0.5*np.sqrt(np.linalg.det(kin['A_cov']))
            H = H_matrix(kin['A_contra'], nu)
            q = Kb*(H @ kin['c'])
            f = A*(Bb.T @ q)
            print(f"{kind:24s} u={lbl:6s} Tinv={mode:4s}  rel.err(f_bend, dW_b/dx) = {rel(f, g):9.3e}")
    print()
