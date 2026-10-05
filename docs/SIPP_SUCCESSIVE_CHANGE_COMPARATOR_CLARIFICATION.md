# SIPP successive-change comparator clarification

This note clarifies terminology only. It does not revise, recompute, or replace any stored numerical result.

The retained single-release SIPP comparator contains 1,057 successive valid occupation changes. Of these, 864 are definitely cross-major. A subset of 721 are also adjacent-calendar-month cross-major changes.

The reported System-B origin-support denominators and route-concordance bounds use the full set of **864 definitely cross-major successive changes**. The **721** count is a timing diagnostic describing the adjacent-calendar-month subset; it is not the denominator used for the reported System-B concordance bounds.

Historical machine-readable material preserves the legacy JSON object name `old_adjacent_month_locked_comparator`. That object contains `all_cross_major_n = 864` and the same reported System-B weighted bounds. The legacy key is retained unchanged for provenance rather than rewritten retrospectively.

The current manuscript and Supplement therefore use the more precise label **single-release successive-change System-B sensitivity** for the 864-based calculations and explicitly identify the 721-event subset as a timing diagnostic.

No scientific value, denominator used in the original concordance calculation, route-concordance endpoint, SIPP weight, model parameter, or conclusion was changed by this terminology correction.
