# System-A certificate results summary

## Fixed analysis network
The certificate calculations condition on the fixed System-A network: 169 support-conditioned origins and the prespecified 335-edge released Top-5/no-backfill graph.

## Origin-side optimal-face bounds
At rho=0.50, the 2024–34 optimal face contains 77 competition-allocation-sensitive origins, 68 competition-neutral origins, 23 origins with no independent route capacity, and 1 zero-supply origin. **No origin is unavoidably competition-squeezed**: the minimum unavoidable competition-loss share is 0.000000%.

For 2025–35 at rho=0.50, the corresponding counts are 75 allocation-sensitive, 70 neutral, 23 no-route-capacity, and 1 zero-supply; again no origin is unavoidably competition-squeezed.

Interpretation: the aggregate competition gap is a **system-level simultaneous-allocation constraint**, not a certificate that a fixed subset of origins must bear the competition loss in every maximum-flow allocation. Different maximum-flow optima can redistribute the shortfall.

## All-minimum-cut bottleneck certificate
At rho=0.50, 18 destination-capacity arcs lie in every minimum cut in 2024–34. In 2025–35, 16 do. Their mandatory sets overlap in 16 destinations (Jaccard 0.8889); arcs 11-2021 and 13-1031 are mandatory only in 2024–34.

Across rho = 0.25, 0.50, 0.75, 1.00, mandatory destination-capacity counts are 33/18/15/7 for 2024–34 and 31/16/15/7 for 2025–35. Seven destinations are mandatory at every tested rho in the 2024–34 vintage: 11-1011, 11-2022, 17-2111, 41-3041, 43-1011, 43-6012, 43-6014.

At rho=0.50, the five receiving-core occupations split into two structural roles. Sales Managers (11-2022), Office/Administrative Support Supervisors (43-1011), and Secretaries/Admin Assistants (43-6014) are both necessary receivers and mandatory min-cut capacity arcs. Bookkeeping/Accounting/Auditing Clerks (43-3031) and Hotel/Motel/Resort Desk Clerks (43-4081) are necessary receivers but are not mandatory min-cut capacity arcs. Thus **necessary use is not the same as capacity bottleneck status**.
