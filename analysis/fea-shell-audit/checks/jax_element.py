"""The whole element, written as an energy, in JAX.
f_int and K_e come from autodiff, so they are exact by construction.
This replaces bending_matrices.py (719 lines) + membrane_matrices.py + the B/K
derivations in shell_element.py with ~40 lines."""
import jax, jax.numpy as jnp
from functools import partial
jax.config.update("jax_enable_x64", True)

S_MAT = jnp.array([[2., 0., 0.], [0., 2., 0.], [0., 0., 1.], [0., 0., 1.]])
PAIRS = ((0, 0), (1, 1), (0, 1), (1, 0))

def _curv(X):
    """Quadratic-fit curvature (4-component Voigt) of a 6-node rotation-free patch."""
    a1 = X[1]-X[0]; a2 = X[2]-X[0]
    ncr = jnp.cross(a1, a2)
    n = ncr/jnp.linalg.norm(ncr)
    g = jnp.array([[a1 @ a1, a1 @ a2], [a2 @ a1, a2 @ a2]])
    gi = jnp.linalg.inv(g)
    c1 = gi[0, 0]*a1 + gi[0, 1]*a2
    c2 = gi[1, 0]*a1 + gi[1, 1]*a2
    b = jnp.stack([X[3]-X[1], X[4]-X[2], X[5]-X[0]])
    off = jnp.array([[1., 0.], [0., 1.], [0., 0.]])
    xi = b @ c1 + off[:, 0]
    et = b @ c2 + off[:, 1]
    z = b @ n
    T = jnp.stack([xi**2-xi, et**2-et, xi*et], axis=1)
    return S_MAT @ jnp.linalg.solve(T, z), g, gi

def _H(gi):
    idx = jnp.array(PAIRS)
    a, bq = idx[:, 0], idx[:, 1]
    A, B = a[:, None], bq[:, None]
    C, D = a[None, :], bq[None, :]
    nu = _H.nu
    return (nu*gi[A, B]*gi[C, D]
            + 0.5*(1.-nu)*(gi[A, C]*gi[B, D] + gi[A, D]*gi[B, C]))

def energy(x_flat, X_flat, E, nu, t):
    x = x_flat.reshape(6, 3); X = X_flat.reshape(6, 3)
    c_cur, g_cur, _ = _curv(x)
    c_ref, g_ref, gi_ref = _curv(X)
    m = jnp.array([0.5*(g_cur[0, 0]-g_ref[0, 0]), 0.5*(g_cur[1, 1]-g_ref[1, 1]),
                   0.5*(g_cur[0, 1]-g_ref[0, 1]), 0.5*(g_cur[1, 0]-g_ref[1, 0])])
    kb = c_ref - c_cur
    idx = jnp.array(PAIRS); a, bq = idx[:, 0], idx[:, 1]
    A, B = a[:, None], bq[:, None]; C, D = a[None, :], bq[None, :]
    H = (nu*gi_ref[A, B]*gi_ref[C, D]
         + 0.5*(1.-nu)*(gi_ref[A, C]*gi_ref[B, D] + gi_ref[A, D]*gi_ref[B, C]))
    Km = E*t/(1.-nu**2); Kbd = E*t**3/(12.*(1.-nu**2))
    area = 0.5*jnp.sqrt(jnp.linalg.det(g_ref))
    return area*(0.5*Km*(m @ H @ m) + 0.5*Kbd*(kb @ H @ kb))

_grad = jax.grad(energy, argnums=0)
_hess = jax.jacfwd(_grad, argnums=0)

@partial(jax.jit, static_argnums=())
def elem_fk(x, X, E, nu, t):
    return _grad(x, X, E, nu, t), _hess(x, X, E, nu, t)

batch_fk = jax.jit(jax.vmap(elem_fk, in_axes=(0, 0, None, None, None)))
batch_f  = jax.jit(jax.vmap(jax.grad(energy, argnums=0), in_axes=(0, 0, None, None, None)))
