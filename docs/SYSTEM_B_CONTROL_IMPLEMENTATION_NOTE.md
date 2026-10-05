# System-B randomized-control implementation note

This note records the implementation rules underlying the reported System-B structural-control results in the Supplementary Information. It documents the calculation lineage; it does not claim a fresh rerun of the unavailable row-level System-B graph.

- **Matched-origin resampling (1,000 replicates):** draws 372 occupations without replacement from the 661-occupation admitted pool within 20 declared strata formed from major SOC, employment, transfers, wage, education, and network outdegree. Analyzed replicates contain no duplicate occupations and use no replacement fallback.
- **Origin-outdegree-preserving reassignment (1,000 replicates):** preserves each origin's post-screen outdegree and samples unique compatible destinations.
- **Directed degree-sequence swap (250 replicates):** each replicate restarts from the observed representative graph, proposes 5m edge swaps where m is the observed edge count, rejects self-loops and duplicate edges, and preserves the in- and out-degree sequences. No formal mixing theorem is claimed.
- **Destination-capacity permutation (1,000 replicates):** holds the observed edge set fixed and permutes destination capacities.
- **Destination attribute-bin matched reassignment (1,000 replicates):** preserves origin outdegree and the distribution of destination capacity, wage, and education bins; the replicate ledger reports zero mean fallback count.

These controls are descriptive structural diagnostics. They are not behavioral validation, causal placebo tests, or evidence of an AI-specific worker-transition effect.
