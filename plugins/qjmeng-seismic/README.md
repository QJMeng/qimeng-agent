# qjmeng-seismic

A public-data seismology MCP plugin for USGS earthquake catalog searches,
hypocentral depth distributions, descriptive focal-mechanism classification,
and Gutenberg-Richter b-value estimation. No API key is required. It uses
the official MCP Python SDK v2 and timed HTTP requests; no agent framework.

## Tools

| Tool | Purpose |
| --- | --- |
| search_earthquakes | Query a circular region and save a complete catalog snapshot |
| summarize_catalog | Depth bins, min/median/max, UTC yearly counts and magnitude types |
| get_event_details | Event information and two-plane rake classification with provenance |
| summarize_mechanisms | Scan a catalog, report mechanism coverage and class fractions |
| calculate_b_value | User-specified Mc, scale selection, MLE b and approximate sampling error |

Search first; use its session catalog_id for later tools. The ID is tied to
that snapshot and expires on process exit. Exports go to a unique work/qjmeng-seismic/session-* directory
under the host working directory and are automatically deleted on session exit.
Crashed-session directories are cleaned at the next startup when their owner
process is no longer running. Active or unrecognized folders are preserved.
Copy a requested permanent export elsewhere before stopping the session. Results expose only short summaries and
artifact paths. The API's independent count must match the downloaded rows;
queries exceeding 20000 events are rejected rather than silently truncated.
Mechanism scans are limited to 500 events, four concurrent calls, 30 seconds
per HTTP request and 240 seconds overall. Set host tool timeout >=250 seconds
for these scans. Other tools may be used on larger accepted catalogs.

## Run in a host

Requires uv; inline metadata selects Python >=3.11 and dependencies.

```sh
claude plugin validate plugins/qjmeng-seismic
claude --plugin-dir plugins/qjmeng-seismic
```

Or register the MCP server with Codex from the harness root:

```sh
codex mcp add qjmeng-seismic -- uv run --script "$PWD/plugins/qjmeng-seismic/server.py"
```

For a long mechanism scan configure `mcp_servers.qjmeng-seismic.tool_timeout_sec`
to 250 in the local Codex config. Retain interactive approval as desired.
Registration makes tools available; it does not automatically load the
Claude-style skill in Codex. Ask the agent to read skills/seismic/SKILL.md.
The harness now loads this plugin in normal web and terminal chat with
`uv run web.py` or `uv run main.py`. The five public-data tools are explicitly
allowed in settings.json. Telegram input mode is available with `uv run main.py --telegram`; send
research parameters in the bot chat and approve any requested skill-read
commands. Full catalogs remain local and final summaries return to the phone.

## Validation case

Ask: "Search earthquakes from 2021-10-21T00:00:00Z to
2026-10-21T00:00:00Z within 100 km of 33.3,-115.8. Use minimum magnitude
3.0 and user-specified Mc=3.0. Summarize depth, mechanism coverage and classes,
and estimate b using raw magnitudes. Also report single-scale b estimates."

These endpoints are UTC midnights, not all of October 21. The center is an
approximation chosen for this exercise. USGS count checks returned 70 events
for M>=3.5 and 205 for M>=3.0 at development time; catalogs can be revised.
A temporary output snapshot includes retrieval time, query, raw GeoJSON and source URL.

## Scientific conventions and limitations

Depths are preferred hypocentral depths in km; bins are [lower,upper).
Depth can be negative; missing depths are excluded with explicit counts.
Mechanism classification is a transparent descriptive rule, not a supplied
USGS event-type field. Use both plane rakes: strike-slip within 30 degrees
of 0/180, reverse 60..120, normal -120..-60, else mixed/oblique. If the two
classes disagree, retain mixed/oblique. Both rakes must be present.
Select the highest weighted usable focal mechanism, then fall back to a
usable tensor; the policy and provenance are explicit. No quality screen is
applied. Rake categories do not establish which plane actually ruptured.
Missing mechanism data and failed detail fetches are reported separately.
Mechanism fractions among usable solutions must accompany total coverage.

The approximate Aki-Utsu estimator is
`b = log10(e) / (mean(M) - Mc + deltaM/2)`.
Default deltaM=0 uses unrounded reported magnitudes. Positive deltaM is only
accepted when magnitudes lie on that grid relative to Mc. No rebinning occurs.
The approximate Shi-Bolt sampling error is
`sigma_b = ln(10)*b^2*sqrt(sum((M-mean(M))^2)/(n*(n-1)))`.
No estimate is returned for n<10 or a constant-magnitude sample; n<50 warns.
These are exploratory estimates: no completeness test, declustering, scale
conversion, truncated-GR fitting or measurement-error propagation is done.
Mixed preferred magnitude types are reported and can be filtered by type.
Filtering the preferred type can itself introduce magnitude-dependent
selection; it is not equivalent to retrieving alternate magnitudes for all
events and constructing a complete homogeneous-scale catalog.
Mc=3.0 is the student's choice, not a demonstrated completeness magnitude.

Sources:
- [USGS FDSN query API](https://earthquake.usgs.gov/fdsnws/event/1/)
- [USGS GeoJSON fields](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php)
- [Marzocchi & Sandri (2003), estimators and binning](https://www.annalsofgeophysics.eu/index.php/annals/article/download/3472/3517/3578)

## Tests and status

```sh
uv run --script plugins/qjmeng-seismic/test_server.py
```

Live public-data validation (network required; no model API calls):

```sh
uv run --script plugins/qjmeng-seismic/test_live.py
```

Status: all ten offline tests passed, including session cleanup and actionable
invalid-ID errors. All five tools ran through a live
stdio SDK client. Codex CLI successfully called search_earthquakes,
summarize_catalog, calculate_b_value (pooled and ml-only), and get_event_details
using temporary MCP configuration. See VALIDATION.md for results and
limitations. Harness integration is implemented; a real-model complete
research chain passed with 205 events, depth/mechanism statistics and b.
The session files were deleted automatically on close. The repeated phone
query passed through all four dependent tools, and the student accepted its
result for this exploratory case. Documented scientific limitations remain.
Harness repository: https://github.com/QJMeng/qimeng-agent .
