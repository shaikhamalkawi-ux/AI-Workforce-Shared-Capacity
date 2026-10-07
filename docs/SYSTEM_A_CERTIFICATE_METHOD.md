# System-A certificate method

## Scientific scope
The certificate calculations condition on the fixed System-A network: the route graph, origin denominator, BLS vectors, and rho grid are held constant while the optimal-flow structure is characterized.

## Inputs
- `baseline_positive_any_support_origins.csv`: fixed 169-origin denominator.
- `frozen_released_top5_edges.csv`: prespecified 335-edge released Top-5/no-backfill graph.
- BLS 2024–34 and 2025–35 model-relevant vectors.

## Origin-side optimal-face bounds
For each origin i and each vintage/rho, total joint flow is fixed at the global maximum F*. Two LPs compute the minimum and maximum origin service over the entire maximum-flow optimal face. The independent-origin ceiling uses the same origin supply and the sum of accessible destination capacities on that origin's prespecified edges.

`unavoidable_competition_loss = independent_ceiling - max_joint_optimal_service`.

This quantity is structural and nonnegative; it is not a worker-level probability, forecast, or causal loss.

## All-minimum-cut bottleneck certificate
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
