# System-A certificate method — Phase 2 / Phase 3

## Scientific scope
This is an additive diagnostic extension of the frozen System-A baseline. It does not change the route graph, origin denominator, BLS vectors, rho grid, or any published baseline calculation.

## Inputs
- `baseline_positive_any_support_origins.csv`: fixed 169-origin denominator.
- `frozen_released_top5_edges.csv`: fixed 335-edge released Top-5/no-backfill graph.
- BLS 2024–34 and 2025–35 vectors from the verified baseline replay.

## Phase 2
For each origin i, and each vintage/rho, total joint flow is fixed at the global maximum F*. Two LPs compute the minimum and maximum origin service over the entire maximum-flow optimal face. The independent-origin ceiling uses the same origin supply and the sum of accessible destination capacities on that origin's frozen edges.

`unavoidable_competition_loss = independent_ceiling - max_joint_optimal_service`.

This quantity is structural and nonnegative; it is not a worker-level probability, forecast, or causal loss.

## Phase 3
A max-flow residual graph is used to identify the canonical minimum and maximum source-side minimum cuts. A destination-capacity arc is:
- in **every** minimum cut if its destination node belongs to the minimum source side;
- in **some** minimum cut if its destination node belongs to the maximum source side;
- in no minimum cut otherwise.

Both canonical cuts are checked to have capacity equal to F*. This classification concerns capacity arcs, not a unique flow allocation.

## Numerical conventions
- rho grid: 0.25, 0.50, 0.75, 1.00.
- LP solver: SciPy HiGHS.
- max-flow/min-cut implementation: deterministic Dinic implementation in `code/systemA_phase23_portable.py`.
- flow equality check tolerance: 1e-6 for cut capacity versus maximum flow; classification residual threshold 1e-9.

## Claim boundaries
These diagnostics do not identify individual transition probabilities, layoffs, worker welfare, local labor-market access, causal AI effects, or the effect of creating additional vacancies.
