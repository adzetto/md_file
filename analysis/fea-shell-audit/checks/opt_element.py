"""Drop-in optimised replacements: identical arithmetic, no np.block / np.cross /
np.linalg.inv on tiny arrays, constants hoisted, Kbg skipped when only f is wanted."""
import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC  = _os.path.abspath(_os.environ.get(
    "FEA_SRC", _os.path.join(_HERE, "..", "..", "..", "Fluid_Structure_Program")))
_OUT  = _os.path.abspath(_os.environ.get("FEA_OUT", _os.path.join(_HERE, "_out")))
_os.makedirs(_OUT, exist_ok=True)
if not _os.path.isdir(_SRC):
    _sys.exit("Set FEA_SRC to the directory holding shell_element.py; looked in " + _SRC)

import sys, numpy as np
SRC=_SRC
sys.path.insert(0,SRC)
import bending_matrices as BM
import shell_element as SE
from mesh import get_patch_coordinates
from shape_functions import shape_function_derivatives
from membrane_matrices import B_m_matrix, K_m_G_matrix
from shell_patch_kinematics import shell_patch_kinematics
from bending_matrices import (B1_matrix, B2_matrix, H1_matrix, H2_matrix,
                              B_b_matrix, apply_bending_edge_transformation,
                              G_matrix, K_matrix, K6_edge_geometric_matrix, cross_matrix)

H2_CONST = H2_matrix()                     # constant: built once, not per element
DN = shape_function_derivatives()
DN0, DN1 = DN[:, 0].copy(), DN[:, 1].copy()

def xcross(a, b):
    return np.array([a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]])

def K4_fast(a1, a2, v):
    n = xcross(a1, a2); L = np.sqrt(n@n); n = n/L
    P = (np.eye(3) - n[:, None]*n)/L
    M1 = cross_matrix(a1); M2 = cross_matrix(a2)
    T1 = P@(M1-M2); T2 = P@M2; T3 = -P@M1
    T1T, T2T, T3T = T1.T, T2.T, T3.T
    v1, v2, v3 = v
    K = np.zeros((18, 18))
    def add(r, c, B): K[3*r:3*r+3, 3*c:3*c+3] += B
    add(0,1, v1*T1T); add(0,3,-v1*T1T)
    add(1,0, v1*T1);  add(1,1, v1*(T2+T2T)); add(1,2, v1*T3); add(1,3,-v1*T2T)
    add(2,1, v1*T3T); add(2,3,-v1*T3T)
    add(3,0,-v1*T1);  add(3,1,-v1*T2); add(3,2,-v1*T3)
    add(0,2, v2*T1T); add(0,4,-v2*T1T)
    add(1,2, v2*T2T); add(1,4,-v2*T2T)
    add(2,0, v2*T1);  add(2,1, v2*T2); add(2,2, v2*(T3+T3T)); add(2,4,-v2*T3T)
    add(4,0,-v2*T1);  add(4,1,-v2*T2); add(4,2,-v2*T3)
    add(0,0, v3*(T1+T1T)); add(0,1, v3*T2); add(0,2, v3*T3); add(0,5,-v3*T1T)
    add(1,0, v3*T2T); add(1,5,-v3*T2T)
    add(2,0, v3*T3T); add(2,5,-v3*T3T)
    add(5,0,-v3*T1);  add(5,1,-v3*T2); add(5,2,-v3*T3)
    return K

def K5_fast(a1, a2, b4, b5, b6, v):
    n = xcross(a1, a2); L = np.sqrt(n@n); n = n/L
    P = np.eye(3) - n[:, None]*n
    M1 = cross_matrix(a1); M2 = cross_matrix(a2)
    M12 = M1 - M2
    v1, v2, v3 = v
    bs = (b4, b5, b6); vs = (v1, v2, v3)
    b_star = v1*b4 + v2*b5 + v3*b6
    NH = n[:, None]*(P@b_star)                 # n h^T
    S, S2 = 1.0/L, 1.0/L**2
    Ls = (M12, M2, -M1)                        # left factors, rows 1..3
    Rs = (M12, M2, -M1)                        # right factors, cols 1..3
    K = np.zeros((18, 18))
    # --- K^a and K^c ---
    for r in range(3):
        Lr = Ls[r]
        LrT = Lr.T
        for c in range(3):
            Rc = Rs[c]
            acc = np.zeros((3, 3))
            for i in range(3):
                bn = bs[i] @ n
                acc += vs[i]*S2*(Lr @ NH @ Rc + bn*(Lr @ P @ Rc))
                acc += vs[i]*S2*(-LrT @ np.outer(bs[i] @ P, n) @ Rc)
            K[3*r:3*r+3, 3*c:3*c+3] += acc
    # --- K^b ---
    Cb = np.zeros((3, 3))
    for i in range(3):
        Cb += vs[i]*S*cross_matrix(bs[i] @ P)
    K[0:3, 3:6] += -Cb; K[0:3, 6:9] += Cb
    K[3:6, 0:3] +=  Cb; K[3:6, 6:9] += -Cb
    K[6:9, 0:3] += -Cb; K[6:9, 3:6] += Cb
    return K

def Kbg_fast(Tinv, q, xi, eta, z, B1, B2, H1, H2, a1, a2, b4, b5, b6, elem, x_curr):
    v_kin = Tinv @ z
    q_vec = np.array([2.0*q[0], 2.0*q[1], q[2]+q[3]])
    v_force = -q_vec @ Tinv
    G = G_matrix(Tinv, q, xi, eta)
    K = K_matrix(Tinv, q, v_kin)
    HH = H1 @ H2
    GH = G @ HH
    B1H = B1 @ HH
    K1 = -HH.T @ (B1.T @ GH) + HH.T @ (K.T @ HH) - (B1H.T @ GH - B1H.T @ GH) - GH.T @ B1H
    TB2H = Tinv @ B2 @ H2
    K2 = HH.T @ (G.T @ TB2H)
    K3 = K2.T if False else (H2.T @ B2.T @ Tinv.T @ GH)
    return (K1 + K2 + K3 + K4_fast(a1, a2, v_force)
            + K5_fast(a1, a2, b4, b5, b6, v_force)
            + K6_edge_geometric_matrix(elem, x_curr, a1, a2, v_force))

def shell_element_fast(elem, NC_ref, NC, GhostNodes, n2i, g2i, E, nu, t,
                       compute="both"):
    pid = elem['patch_ids']
    X_ref = get_patch_coordinates(pid, NC_ref, GhostNodes, n2i, g2i, NC_ref=NC_ref, config='reference')
    x_curr = get_patch_coordinates(pid, NC, GhostNodes, n2i, g2i, config='current')
    kin = shell_patch_kinematics(X_ref, x_curr-X_ref)
    Tinv = kin['Tinv_ref']; S = kin['S']
    A_tri = 0.5*np.sqrt(np.linalg.det(kin['A_cov']))
    H = SE.H_matrix(kin['A_contra'], nu)
    p, q = SE.stress_resultants(kin['m'], kin['c'], H, E, nu, t)
    B1 = B1_matrix(Tinv, kin['xi_curr'], kin['eta_curr'], kin['z_curr'])
    H1 = H1_matrix(kin['a1_contra'], kin['a2_contra'], kin['b4'], kin['b5'], kin['b6'])
    B2 = B2_matrix(kin['a1_cov'], kin['a2_cov'], kin['b4'], kin['b5'], kin['b6'])
    B_b = B_b_matrix(B1, B2, H1, H2_CONST, S, Tinv)
    Bb_mod, Y = apply_bending_edge_transformation(B_b, elem, X_ref, x_curr, kin)
    B_m = B_m_matrix(kin)
    f = None; Ke = None
    if compute in ("force", "both"):
        f = A_tri*(B_m.T @ p) + A_tri*(Bb_mod.T @ q)
    if compute in ("stiffness", "both"):
        Kbg = Kbg_fast(Tinv, q, kin['xi_curr'], kin['eta_curr'], kin['z_curr'],
                       B1, B2, H1, H2_CONST, kin['a1_cov'], kin['a2_cov'],
                       kin['b4'], kin['b5'], kin['b6'], elem, x_curr)
        Hb = E*t**3/(12*(1-nu**2))*H
        Hm = E*t/(1-nu**2)*H
        Kmg = K_m_G_matrix(p, DN0, DN1)
        Ke = (B_m.T @ Hm @ B_m + Kmg)*A_tri + (Bb_mod.T @ Hb @ Bb_mod + Y.T @ Kbg @ Y)*A_tri
    return f, Ke
