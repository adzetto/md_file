import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SRC  = _os.path.abspath(_os.environ.get(
    "FEA_SRC", _os.path.join(_HERE, "..", "..", "..", "Fluid_Structure_Program")))
_OUT  = _os.path.abspath(_os.environ.get("FEA_OUT", _os.path.join(_HERE, "_out")))
_os.makedirs(_OUT, exist_ok=True)
if not _os.path.isdir(_SRC):
    _sys.exit("Set FEA_SRC to the directory holding shell_element.py; looked in " + _SRC)

import sys, os, time, numpy as np
SRC=_SRC
sys.path.insert(0,SRC)
sys.path.insert(0,_HERE)
os.chdir(SRC)
import jax.numpy as jnp
from jax_element import elem_fk, batch_fk, batch_f, energy
from shell_patch_kinematics import shell_patch_kinematics
import shell_element as SE

E,nu,t = 2e5, 0.35, 6e-4
BASE=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[1.,1.,0.],[-1.,1.,0.],[0.5,-1.,0.]])
def rel(a,b): return np.linalg.norm(np.asarray(a)-np.asarray(b))/max(np.linalg.norm(np.asarray(b)),1e-300)
def asym(K): K=np.asarray(K); return np.linalg.norm(K-K.T)/max(np.linalg.norm(K),1e-300)

print("="*84)
print("JAX element (energy + autodiff) vs the hand-derived one, and vs finite differences")
print("="*84)
rng=np.random.default_rng(4)
for kind in ('flat','curved'):
    X=BASE.copy(); X[:,:2]+=0.05*rng.standard_normal((6,2))
    if kind=='curved': X[:,2]=0.15*(X[:,0]**2+X[:,1]**2)
    for amp in (1e-3,1e-2,1e-1):
        x=X+amp*np.random.default_rng(9).standard_normal(X.shape)
        f_j,K_j = elem_fk(jnp.array(x.ravel()), jnp.array(X.ravel()), E, nu, t)
        f_j=np.asarray(f_j); K_j=np.asarray(K_j)
        # finite-difference gradient of the same energy
        g=np.zeros(18)
        for i in range(18):
            h=1e-7*max(1.,abs(x.ravel()[i]))
            xp=x.ravel().copy(); xp[i]+=h; xm=x.ravel().copy(); xm[i]-=h
            g[i]=(float(energy(jnp.array(xp),jnp.array(X.ravel()),E,nu,t))
                  -float(energy(jnp.array(xm),jnp.array(X.ravel()),E,nu,t)))/(2*h)
        # the code's own f_int (all-internal patch)
        kin=shell_patch_kinematics(X,x-X)
        from membrane_matrices import B_m_matrix
        from bending_matrices import (B1_matrix,B2_matrix,H1_matrix,H2_matrix,B_b_matrix)
        Tinv=kin['Tinv_ref']
        Hc=SE.H_matrix(kin['A_contra'],nu); p,q=SE.stress_resultants(kin['m'],kin['c'],Hc,E,nu,t)
        Bb=B_b_matrix(B1_matrix(Tinv,kin['xi_curr'],kin['eta_curr'],kin['z_curr']),
                      B2_matrix(kin['a1_cov'],kin['a2_cov'],kin['b4'],kin['b5'],kin['b6']),
                      H1_matrix(kin['a1_contra'],kin['a2_contra'],kin['b4'],kin['b5'],kin['b6']),
                      H2_matrix(),kin['S'],Tinv)
        A=0.5*np.sqrt(np.linalg.det(kin['A_cov']))
        f_code=A*(B_m_matrix(kin).T@p + Bb.T@q)
        print(f"  {kind:7s} u={amp:6.0e} : jax vs FD grad = {rel(f_j,g):.2e} | "
              f"asym(K_jax) = {asym(K_j):.2e} | code f_int vs jax f_int = {rel(f_code,f_j):.3e}")
print()
print("="*84)
print("THROUGHPUT:  hand-written numpy element  vs  JAX vmap (CPU)")
print("="*84)
from mesh import build_element_topology, build_element_patch_ids, apply_rot_bc, get_patch_coordinates
from ghost import build_ghost_nodes
from roof_mesh import generate_cylindrical_roof_mesh
from shell_element import shell_element_routine
for n in (16,32,48):
    NC0,EC=generate_cylindrical_roof_mesh(2540.,508.,0.1,n,n)
    n2i={int(NC0[i,0]):i for i in range(NC0.shape[0])}
    Elements,e2i,_=build_element_topology(EC,NC0); apply_rot_bc(Elements,np.zeros((0,3),int))
    G,GO=build_ghost_nodes(Elements,NC0,n2i); g2i={g['ID']:i for i,g in enumerate(G)}
    for g in G: g['X_ref']=g['X'].copy()
    build_element_patch_ids(Elements,GO)
    NC=NC0.copy()
    Xs=np.array([get_patch_coordinates(el['patch_ids'],NC0,G,n2i,g2i,NC_ref=NC0,config='reference').ravel()
                 for el in Elements])
    xs=np.array([get_patch_coordinates(el['patch_ids'],NC,G,n2i,g2i,config='current').ravel()
                 for el in Elements])
    Ej,nuj,tj = 3.10275e3,0.3,12.7
    t0=time.perf_counter()
    for el in Elements: shell_element_routine(el,NC0,NC,G,n2i,g2i,Ej,nuj,tj,compute="both")
    t_np=time.perf_counter()-t0
    xj=jnp.array(xs); Xj=jnp.array(Xs)
    r=batch_fk(xj,Xj,Ej,nuj,tj); jax_block=r[0].block_until_ready()
    t0=time.perf_counter()
    for _ in range(5):
        r=batch_fk(xj,Xj,Ej,nuj,tj); r[0].block_until_ready(); r[1].block_until_ready()
    t_jx=(time.perf_counter()-t0)/5
    t0=time.perf_counter()
    for _ in range(5):
        rf=batch_f(xj,Xj,Ej,nuj,tj); rf.block_until_ready()
    t_jf=(time.perf_counter()-t0)/5
    print(f"  nelem={len(Elements):5d}   numpy(f+K) {t_np:8.3f}s   jax(f+K) {t_jx:8.4f}s "
          f"[{t_np/t_jx:6.1f}x]   jax(f only) {t_jf:8.4f}s [{t_np/t_jf:6.1f}x]")
