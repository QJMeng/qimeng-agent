---
name: seismic
description: Use for USGS earthquake catalog queries, depth distributions, focal-mechanism summaries, or Gutenberg-Richter b-value estimates in a specified time and region.
---

1. Establish UTC start/end times, center latitude/longitude in degrees,
   epicentral radius in km, and minimum query magnitude. Run search_earthquakes.
   Reuse the returned catalog_id for all statistics; IDs expire on server exit.
2. Use summarize_catalog for hypocentral depths and magnitude-type counts.
   Negative depths and missing values must remain explicit. The circular
   default region approximates Salton Sea; it is not a state or basin boundary.
3. Use get_event_details or summarize_mechanisms for rake-based classification.
   Prefer usable focal-mechanism products, then usable moment tensors, ordered
   by preferred weight and update time within each type. Preserve provenance.
   This policy is ours; do not claim it is the overall USGS preferred solution.
   Both planes must be present: classify strike-slip within 30 degrees of 0 or
   180, reverse within 30 degrees of +90, and normal within 30 degrees of -90.
   Other or disagreeing classifications are mixed/oblique. Missing is unknown;
   network failures are fetch_failed. Do not infer a mechanism from geography.
   Reverse includes but does not distinguish low-angle thrusts. Do not identify
   the actual fault plane from the two nodal planes alone. No mechanism quality
   screen is applied. Report coverage and both percentage denominators.
4. For b, ask/confirm Mc separately from the query cutoff. Never claim Mc has
   been estimated or validated. calculate_b_value uses all qualifying events,
   not just events with mechanisms. Default bin width zero uses raw preferred
   magnitudes. A positive width requires a matching grid and applies a half-bin
   correction; never round/rebin silently. Report b, approximate 1-sigma error,
   n, Mc, bin width, scales, and warnings. If mixed scales occur, also compute
   single-scale results where samples permit, but explain that filtering the
   preferred type can select events differently at different magnitudes;
   this is not equivalent to constructing a complete homogeneous-scale catalog.
   No declustering or magnitude
   homogenization is performed. Do not interpret differences as physical
   changes without completeness, uncertainty, scale, and clustering checks.

Current validation case: 2021-10-21T00:00:00Z through
2026-10-21T00:00:00Z (inclusive), center 33.3 N, 115.8 W, radius 100 km,
query minimum 3.0 and user-specified Mc=3.0. This replaces the initial Mc=3.5.
Use fixed dates to reproduce the case; do not silently slide the window.

Keep phone replies short and link local artifacts when appropriate. Full
catalogs and mechanism rows are written under work/qjmeng-seismic/session-* in the host
working directory and are automatically deleted when the MCP session closes.
Copy any explicitly requested permanent export elsewhere before stopping. Public-data file export is the only local write; no user
analysis code or shell command is executed by these tools.
