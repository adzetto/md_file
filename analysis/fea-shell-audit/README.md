# Rotation-free shell audit

A line-level correctness and performance review of the `Fluid_Structure_Program` six-node
rotation-free Kirchhoff–Love shell code, plus the executable checks that produced every
number in it.

The written report is `shell-audit.html`. Open it in a browser.

## What is in here

| Path | Contents |
|---|---|
| `shell-audit.html` | The report: 9 formulation findings, 5 driver findings, 7 verified-correct subsystems, benchmark reproduction, performance measurements |
| `checks/` | 21 verification scripts, each importing the unmodified shell source |
| `checks/opt_element.py` | Drop-in optimised element, bit-identical output, used for the "configuration B" timings |
| `checks/jax_element.py` | The same element written as a scalar energy in JAX; force and tangent come from `jax.grad` and `jax.jacfwd` |
| `cpp/` | The element energy in templated C++ with forward-mode dual numbers, and the benchmark driver |

## Running the checks

The scripts do not vendor the shell source. Point `FEA_SRC` at the directory that holds
`shell_element.py`:

```bash
export FEA_SRC=/path/to/Fluid_Structure_Program
python3 checks/t2_bending_isolated.py
```

Without `FEA_SRC` the scripts look for `Fluid_Structure_Program` three levels above
`checks/` and exit with a message if it is not there. Output files go to `checks/_out/`,
or to `FEA_OUT` if set.

Requirements: `numpy`, `scipy`, `matplotlib` (only for the drivers), `jax` for
`t9_jax_check.py` and `t20_endtoend.py`.

## Which script produces which finding

| Script | Finding | Runtime |
|---|---|---|
| `t1_kinematics.py` | rigid-body invariance, `B_m`, first pass on `B_b` and `f_int` | seconds |
| `t2_bending_isolated.py` | F1 (reference vs current parametrisation), F2 (missing `H1` term) | seconds |
| `t3_tangent.py` | F4, membrane and bending tangent blocks compared separately | seconds |
| `t4_edge_and_crease.py` | F5 (clamped-edge `Y` block), F6 (crease `K_mat2`) | seconds |
| `t5_crease_geo.py` | F6 split into material and geometric parts | seconds |
| `t6_plate_convergence.py` | F9, clamped versus simply supported convergence | ~3 min |
| `t7_global_consistency.py` | F3, the 16.3 % force/energy-gradient gap | ~10 min |
| `t13_distorted.py` | F8, mesh distortion and topology sensitivity | ~5 min |
| `t14_bending_patch_test.py` | bending patch test on four mesh types | ~1 min |
| `t15_spectrum.py` | eigenvalue check ruling out a spurious mode on the union-jack mesh | ~1 min |
| `t16_energy_consistency.py` | manufactured-solution bending energy, interior and full domain | ~5 min |
| `t17_unionjack.py` | F8, the 33.6 % non-convergent plate solution | ~5 min |
| `t18_energy_fields.py` | discrete bending energy for six imposed fields | ~3 min |
| `t19_freeedge.py` | F8 mechanism: ghost parametric positions per local edge index | seconds |
| `t10_micro.py` | primitive costs (`np.cross`, `np.block`, `np.linalg.inv`, `H2_matrix`) | ~1 min |
| `t11_opt_bench.py` | optimised element versus original, dense versus COO scatter | ~2 min |
| `t12_verify_fast.py` | proves the optimised element is numerically identical on a deformed mesh | seconds |
| `t20_endtoend.py` | one Newton iteration, three configurations | ~5 min |
| `prof_element.py` | `cProfile` of one stiffness assembly | ~1 min |
| `t8_solver_scaling.py` | dense versus sparse storage and factorisation | ~3 min |
| `t9_jax_check.py` | JAX element against finite differences, and throughput | ~3 min |
| `bench_cantilever.py` | the cantilever benchmark under three variants | ~15 min each |

`bench_cantilever.py` takes a variant argument:

```bash
python3 checks/bench_cantilever.py as_shipped     # unmodified
python3 checks/bench_cantilever.py tinv_curr      # F1 repaired
python3 checks/bench_cantilever.py tinv_curr_h1   # F1 and F2 repaired
```

The last two patch `shell_element.py` in memory; the file on disk is not touched.

## Building the C++ benchmark

```bash
g++ -O3 -march=native -DNDEBUG -I/usr/include/eigen3 cpp/bench.cpp -o cpp/bench
./cpp/bench 4608
```

Eigen 3.4 supplies the sparse LDLT. The element energy in `cpp/element.hpp` is templated
on the scalar type, so the same source yields the value, the gradient (18-wide dual), and
the Hessian (nested duals).

## The finding IDs

| ID | Summary | Severity |
|---|---|---|
| F1 | `B_b` built from `Tinv_ref` while `c_curr` uses `Tinv_curr` | wrong answer |
| F2 | `H1_matrix` omits `−z_i (a^α · δn)` | wrong answer |
| F3 | Assembled `F_int` is not the gradient of the assembled energy | wrong answer |
| F4 | Bending tangent is not the Jacobian of the bending force | convergence |
| F5 | Clamped-edge `Y` drops `∂x_ghost/∂x_F`; the disabled line has the wrong sign | latent |
| F6 | `constraint_penalty.py:92` transposes one outer product | one-line fix |
| F7 | Cosine-based crease penalty has stiffness `κ sin²θ₀` | modelling |
| F8 | Free-edge ghost condition depends on the local edge index | wrong answer |
| F9 | Clamped edges converge at about `h^1.8` | accuracy |
| F10 | No driver checks Newton convergence before committing the step | correctness |
| F11 | `K_bending_geometric` is built even for `compute="force"` | performance |
| F12 | `jax_penalty_module` is imported but absent | blocks 3 drivers |
| F13 | `K_load_global` assembled then discarded | dead work |
| F14 | Three unused modules | cleanup |
