"""Where the numpy overhead really is: micro-costs of the primitives used per element."""
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
sys.path.insert(0,SRC); os.chdir(SRC)
import bending_matrices as BM

def tm(f, n=20000):
    f(); t0=time.perf_counter()
    for _ in range(n): f()
    return 1e6*(time.perf_counter()-t0)/n     # microseconds per call

a=np.random.default_rng(0).standard_normal(3); b=np.random.default_rng(1).standard_normal(3)
A3=np.random.default_rng(2).standard_normal((3,3)); A2=np.eye(2)+0.1
Z=np.zeros((3,3)); T=np.eye(3)
print("primitive costs (microseconds per call):")
print(f"  np.cross(3,3)                 {tm(lambda: np.cross(a,b)):8.3f}")
print(f"  explicit cross (3 mul-sub)    {tm(lambda: np.array([a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]])):8.3f}")
print(f"  np.linalg.inv(2x2)            {tm(lambda: np.linalg.inv(A2)):8.3f}")
print(f"  np.linalg.inv(3x3)            {tm(lambda: np.linalg.inv(A3)):8.3f}")
print(f"  np.outer(3,3)                 {tm(lambda: np.outer(a,b)):8.3f}")
print(f"  a[:,None]*b                   {tm(lambda: a[:,None]*b):8.3f}")
print(f"  np.zeros((18,18))             {tm(lambda: np.zeros((18,18))):8.3f}")
blk=[[T,Z,Z,Z,Z,Z],[Z,T,Z,Z,Z,Z],[Z,Z,T,Z,Z,Z],[Z,Z,Z,T,Z,Z],[Z,Z,Z,Z,T,Z],[Z,Z,Z,Z,Z,T]]
print(f"  np.block(6x6 of 3x3)          {tm(lambda: np.block(blk), 3000):8.3f}")
def slices():
    M=np.zeros((18,18))
    for i in range(6):
        for j in range(6): M[3*i:3*i+3,3*j:3*j+3]=blk[i][j]
    return M
print(f"  same via slice assignment     {tm(slices, 3000):8.3f}")
M18=np.random.default_rng(3).standard_normal((18,18))
print(f"  18x18 @ 18x18                 {tm(lambda: M18@M18):8.3f}")
print()
a1=np.random.default_rng(5).standard_normal(3); a2=np.random.default_rng(6).standard_normal(3)
v=np.array([1.,2.,3.]); b4,b5,b6=a,b,a+b
print("element sub-blocks (microseconds per call):")
print(f"  H2_matrix()  [constant!]      {tm(BM.H2_matrix, 3000):8.3f}")
print(f"  K4_geometric_matrix           {tm(lambda: BM.K4_geometric_matrix(a1,a2,v), 2000):8.3f}")
print(f"  K5_geometric_matrix           {tm(lambda: BM.K5_geometric_matrix(a1,a2,b4,b5,b6,v), 1000):8.3f}")
elem={'edge_bc':['free',None,None]}
xc=np.random.default_rng(7).standard_normal((6,3))
print(f"  K6_edge_geometric_matrix      {tm(lambda: BM.K6_edge_geometric_matrix(elem,xc,a1,a2,v), 3000):8.3f}")
print()

# ---- optimised K4 : same maths, slice assignment, no np.block ----
def K4_fast(a1_cov,a2_cov,v_force):
    n=np.array([a1_cov[1]*a2_cov[2]-a1_cov[2]*a2_cov[1],
                a1_cov[2]*a2_cov[0]-a1_cov[0]*a2_cov[2],
                a1_cov[0]*a2_cov[1]-a1_cov[1]*a2_cov[0]])
    L=np.sqrt(n@n); n=n/L
    P=(np.eye(3)-n[:,None]*n)/L
    M1=BM.cross_matrix(a1_cov); M2=BM.cross_matrix(a2_cov)
    T1=P@(M1-M2); T2=P@M2; T3=-P@M1
    v1,v2,v3=v_force
    K=np.zeros((18,18))
    def add(r,c,B):
        K[3*r:3*r+3,3*c:3*c+3]+=B
    T1T,T2T,T3T=T1.T,T2.T,T3.T
    # F4 (weight v1)
    add(0,1,v1*T1T); add(0,3,-v1*T1T)
    add(1,0,v1*T1);  add(1,1,v1*(T2+T2T)); add(1,2,v1*T3); add(1,3,-v1*T2T)
    add(2,1,v1*T3T); add(2,3,-v1*T3T)
    add(3,0,-v1*T1); add(3,1,-v1*T2); add(3,2,-v1*T3)
    # F5 (weight v2)
    add(0,2,v2*T1T); add(0,4,-v2*T1T)
    add(1,2,v2*T2T); add(1,4,-v2*T2T)
    add(2,0,v2*T1);  add(2,1,v2*T2); add(2,2,v2*(T3+T3T)); add(2,4,-v2*T3T)
    add(4,0,-v2*T1); add(4,1,-v2*T2); add(4,2,-v2*T3)
    # F6 (weight v3)
    add(0,0,v3*(T1+T1T)); add(0,1,v3*T2); add(0,2,v3*T3); add(0,5,-v3*T1T)
    add(1,0,v3*T2T); add(1,5,-v3*T2T)
    add(2,0,v3*T3T); add(2,5,-v3*T3T)
    add(5,0,-v3*T1); add(5,1,-v3*T2); add(5,2,-v3*T3)
    return K
K_ref=BM.K4_geometric_matrix(a1,a2,v); K_new=K4_fast(a1,a2,v)
print(f"  K4_fast matches original?  max|diff| = {np.max(np.abs(K_ref-K_new)):.3e}")
print(f"  K4_fast cost                  {tm(lambda: K4_fast(a1,a2,v), 3000):8.3f}  us  "
      f"(vs {tm(lambda: BM.K4_geometric_matrix(a1,a2,v),2000):.3f} us original)")
