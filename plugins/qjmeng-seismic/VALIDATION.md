# Salton Sea validation case

## Query and provenance

- Source: USGS ComCat FDSN earthquake service.
- UTC interval: 2021-10-21T00:00:00Z through 2026-10-21T00:00:00Z, inclusive.
- Approximate center: latitude 33.3 degrees, longitude -115.8 degrees.
- Epicentral radius: 100 km; no depth cutoff.
- Earthquake events only; query minimum magnitude 3.0.
- User-specified Mc: 3.0, replacing the initial choice 3.5.
- Development retrieval: October 21, 2026 UTC. Catalogs are revisable.
- API count and downloaded event count agreed: 205; no truncation.

Independent count checks for the same time and region returned 70 events
at M>=3.5, 205 at M>=3.0, and 600 at M>=2.5.
The fixed end date is midnight at the start of October 21, not its end.

Historical JSON reports and raw catalog snapshots were deleted at the
student's request. The scientific results below remain as a compact English
validation record. Rerun the live test to regenerate temporary source data;
the MCP session automatically removes it on exit.

## Depths and mechanism classification

205 events have usable depths: minimum 1.87 km, median 9.67 km,
maximum 22.82 km. These are preferred hypocentral depths.

181/205 events (88.29%) have usable two-plane rake parameters. There were
24 unknown mechanisms and zero failed detail fetches in this run.

| Descriptive class | Count | Fraction of 181 usable mechanisms |
| --- | ---: | ---: |
| Strike-slip | 146 | 80.66% |
| Reverse | 1 | 0.55% |
| Normal | 6 | 3.31% |
| Mixed/oblique | 28 | 15.47% |

These are outputs of the README's explicit rake rule, not a validated
tectonic interpretation or an identification of the ruptured plane.
No quality filtering was performed. Coverage and product selection can bias
these fractions. During a session, the per-event file records sources, product selection,
both rakes and classifications for scientific review; it is deleted on exit.

## b-value estimates

Method: unrounded preferred magnitudes, deltaM=0, Aki-Utsu maximum likelihood,
with approximate Shi-Bolt 1-sigma sampling errors. No mechanism filter applied.

| Preferred magnitude selection | n | b | Approximate 1-sigma |
| --- | ---: | ---: | ---: |
| All (156 ml, 46 mw, 3 mlr) | 205 | 0.9660 | 0.0599 |
| ml only | 156 | 1.5201 | 0.0851 |
| mw only | 46 | 0.4339 | 0.0272 |
| mlr only | 3 | Not estimated | Insufficient sample |

The pooled value is exploratory because scales are mixed. The per-type
values are diagnostic only: preferred magnitude type selection can vary
with event size, and a type-filtered subset is not a complete homogeneous
catalog. In particular, the ml subset's observed maximum is only 3.95.
Do not interpret differences between these estimates as physical differences.

Mc has not been estimated or validated, and no declustering, scale conversion,
finite-upper-bound GR fitting, or measurement-error propagation was performed.
The reported errors exclude these systematic uncertainties. A research-grade
analysis should retrieve consistent magnitudes (including alternate magnitude
solutions where appropriate), evaluate completeness and magnitude range, and
assess clustering and model adequacy.

## Verification status

Seven offline tests passed: synthetic exponential-population b recovery,
bin correction/grid rejection, magnitude selection and small/degenerate
samples, negative/missing/boundary depths, mechanism ambiguity and product
ranking, MCP discovery/dispatch, and count-mismatch refusal.

All five tools were exercised through a real stdio MCP client with live
USGS data. Codex CLI v0.163.0-alpha.10.2 also successfully called
search_earthquakes, summarize_catalog, calculate_b_value (pooled and ml-only),
and get_event_details. It independently obtained the same counts, depths and
b estimates. The per-type selection-bias warning was added during this test;
the scientific review should use the cautions in this document.

The student subsequently accepted the result of the repeated phone query.
That query successfully called catalog search, depth summary, mechanism
summary and b estimation through the student's own harness. This satisfies
the course's exploratory scientific-review checkpoint, while retaining all
the completeness, magnitude-scale and classification limitations above.
