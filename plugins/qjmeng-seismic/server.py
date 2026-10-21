# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2,<3", "httpx>=0.28,<1"]
# ///
"""Read-only USGS queries with reproducible local snapshots and summaries."""
import asyncio
import hashlib
import json
import logging
import math
import os
import re
import shutil
import statistics
import tempfile
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

API = "https://earthquake.usgs.gov/fdsnws/event/1"
catalogs = {}
details = {}
BASE_OUTPUT = Path.cwd() / "work" / "qjmeng-seismic"
OUTPUT = None


def cleanup_stale_sessions(base):
    """Remove only recognized session folders whose recorded owner has exited."""
    for folder in base.glob('session-*'):
        if not folder.is_dir() or folder.is_symlink():
            continue
        try:
            pid = json.loads((folder / 'owner.json').read_text())['pid']
            if not isinstance(pid, int) or pid <= 0:
                continue
            os.kill(pid, 0)
        except ProcessLookupError:
            shutil.rmtree(folder)
        except (OSError, KeyError, ValueError):
            # Unknown folders and live/inaccessible processes are left alone.
            continue


@asynccontextmanager
async def lifespan(server):
    global OUTPUT
    BASE_OUTPUT.mkdir(parents=True, exist_ok=True)
    cleanup_stale_sessions(BASE_OUTPUT)
    with tempfile.TemporaryDirectory(prefix='session-', dir=BASE_OUTPUT) as directory:
        OUTPUT = Path(directory)
        (OUTPUT / 'owner.json').write_text(json.dumps({'pid': os.getpid()}))
        try:
            yield {}
        finally:
            OUTPUT = None
            catalogs.clear()
            details.clear()


mcp = MCPServer("qjmeng-seismic", lifespan=lifespan)
logging.getLogger("httpx").setLevel(logging.WARNING)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def utc(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise ValueError("Use ISO8601 dates/times, e.g. 2021-10-21T00:00:00Z.") from None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def save(name, data):
    if OUTPUT is None:
        raise RuntimeError('Start an MCP session before exporting results.')
    path = OUTPUT / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False))
    return str(path.resolve())


async def fetch(path, parameters):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10)) as client:
            response = await client.get(API + path, params=parameters)
        if response.status_code == 204:
            return {"features": [], "metadata": {"count": 0}}
        if response.status_code != 200:
            raise RuntimeError(f"USGS HTTP {response.status_code}; narrow the query, check parameters, or retry later.")
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise RuntimeError("USGS network/JSON failure; retry later or use a smaller query.") from None


def event_row(event):
    p = event.get("properties", {})
    coords = event.get("geometry", {}).get("coordinates", [None, None, None])
    return {"id": event["id"], "time_utc": datetime.fromtimestamp(p["time"] / 1000, timezone.utc).isoformat(),
            "magnitude": number(p.get("mag")), "magnitude_type": p.get("magType") or "unknown",
            "longitude_deg": coords[0], "latitude_deg": coords[1], "depth_km": number(coords[2]),
            "place": p.get("place"), "status": p.get("status"), "url": p.get("url"),
            "products": p.get("types", "")}


def catalog(catalog_id):
    if catalog_id not in catalogs:
        known = ', '.join(catalogs.keys()) or '(none)'
        raise ToolError("Unknown catalog_id. Copy the exact catalog_id from the most recent search_earthquakes result for the intended query; do not guess. Available session catalog IDs: " + known)
    return catalogs[catalog_id]


@mcp.tool()
async def search_earthquakes(starttime: str, endtime: str, latitude: float = 33.3,
                            longitude: float = -115.8, radius_km: float = 100,
                            min_magnitude: float = 3.0) -> dict:
    """Fetch a complete earthquake-only USGS catalog for a circular region.

    Times are ISO8601 UTC unless an offset is explicit; endtime is inclusive.
    Example: 2021-10-21 to 2026-10-21 means midnight UTC at each endpoint.
    latitude/longitude are degrees; radius_km is epicentral distance in km.
    Default center 33.3,-115.8 approximates Salton Sea, not a shoreline polygon.
    min_magnitude is a query cutoff, NOT an automatically validated Mc.
    Returns a session catalog_id, count, preview, source URL and full snapshot
    path. Refuses >20000 events rather than analyzing a truncated catalog.
    Snapshot and computed result files are temporary and deleted on session
    exit. Copy needed files elsewhere before stopping; no automatic retention.
    Use this before summary, mechanism, or b-value tools. No credentials needed.
    """
    if not all(math.isfinite(x) for x in (latitude, longitude, radius_km, min_magnitude)):
        raise ValueError("Numeric parameters must be finite.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or not 0 < radius_km <= 20001.6:
        raise ValueError("Check latitude [-90,90], longitude [-180,180], and radius (0,20001.6] km.")
    start, end = utc(starttime), utc(endtime)
    if start >= end or end > datetime.now(timezone.utc):
        raise ValueError("Use starttime < endtime and an endtime no later than now.")
    params = {"starttime": start.isoformat(), "endtime": end.isoformat(), "latitude": latitude,
              "longitude": longitude, "maxradiuskm": radius_km, "minmagnitude": min_magnitude,
              "eventtype": "earthquake"}
    before = await fetch("/count", {**params, "format": "geojson"})
    expected = before["count"]
    if expected > 20000:
        raise ValueError(f"Query has {expected} events; narrow time/region or raise min_magnitude (limit 20000).")
    raw = await fetch("/query", {**params, "format": "geojson", "orderby": "time-asc", "limit": 20000})
    events = raw.get("features", [])
    ids = [e["id"] for e in events]
    if len(events) != expected or len(set(ids)) != len(ids):
        raise RuntimeError("USGS catalog changed or count/IDs disagree; rerun before interpreting statistics.")
    rows = [event_row(e) for e in events]
    retrieved = datetime.now(timezone.utc).isoformat()
    key = hashlib.sha256(json.dumps([params, retrieved, ids], sort_keys=True).encode()).hexdigest()[:16]
    payload = {"catalog_id": key, "query": params, "retrieved_utc": retrieved,
               "count": len(rows), "events": rows, "source_url": str(httpx.URL(API + "/query", params={**params, "format": "geojson"}))}
    path = save(f"catalog-{key}.json", {**payload, "raw_geojson": raw})
    catalogs[key] = payload
    return {k: v for k, v in payload.items() if k != "events"} | {
        "truncated": False, "snapshot_path": path, "preview": rows[:5],
        "status_counts": dict(Counter(r['status'] or 'unknown' for r in rows)),
        "events_advertising_mechanism_products": sum(any(k in r['products'] for k in ('focal-mechanism', 'moment-tensor')) for r in rows),
        "magnitude_types": dict(Counter(r["magnitude_type"] for r in rows)),
        "note": "USGS preferred magnitudes may mix scales; Mc and scientific quality are not validated."}


@mcp.tool()
def summarize_catalog(catalog_id: str, depth_bin_km: float = 10) -> dict:
    """Summarize a session catalog's depths, yearly counts, and magnitude types.

    depth_bin_km is the positive bin width in km (default 10). Bins are
    [lower,upper), including negative depths rather than silently dropping
    them. Depth means preferred hypocentral depth, not centroid depth.
    Missing depths are counted separately. Example catalog_id comes from
    search_earthquakes; no network call or mechanism assumption is made.
    """
    data = catalog(catalog_id)
    if not math.isfinite(depth_bin_km) or depth_bin_km <= 0:
        raise ValueError("depth_bin_km must be a positive finite number.")
    rows = data["events"]
    depths = [r["depth_km"] for r in rows if r["depth_km"] is not None]
    bins = Counter(math.floor(d / depth_bin_km) for d in depths)
    result = {"catalog_id": catalog_id, "count": len(rows), "depth_valid": len(depths),
              "depth_missing": len(rows) - len(depths),
              "depth_km": {"min": min(depths), "median": statistics.median(depths), "max": max(depths)} if depths else None,
              "depth_bins": [{"lower_km": k * depth_bin_km, "upper_km_exclusive": (k + 1) * depth_bin_km, "count": bins[k]} for k in sorted(bins)],
              "yearly_counts_utc": dict(sorted(Counter(r["time_utc"][:4] for r in rows).items())),
              "magnitude_types": dict(Counter(r["magnitude_type"] for r in rows)),
              "largest_events": sorted(rows, key=lambda r: r["magnitude"] if r["magnitude"] is not None else -math.inf, reverse=True)[:3]}
    return result


def rake_class(rake):
    rake = (rake + 180) % 360 - 180
    if abs(rake) <= 30 or abs(rake) >= 150:
        return "strike-slip"
    if 60 <= rake <= 120:
        return "reverse"
    if -120 <= rake <= -60:
        return "normal"
    return "mixed/oblique"


def mechanism(event):
    products = event.get("properties", {}).get("products", {})
    # Prefer focal-mechanism products (often first-motion) over moment tensors.
    # Within each type select the highest weighted usable product, then newest.
    for kind in ("focal-mechanism", "moment-tensor"):
        ranked = sorted((p for p in products.get(kind, []) if p.get("status") != "DELETE"),
                        key=lambda p: (number(p.get("preferredWeight")) or 0, number(p.get("updateTime")) or 0), reverse=True)
        for p in ranked:
            props = p.get("properties", {})
            rakes = [number(props.get(f"nodal-plane-{n}-rake")) for n in (1, 2)]
            if any(r is None or not -180 <= r <= 180 for r in rakes):
                continue
            classes = [rake_class(r) for r in rakes]
            category = classes[0] if classes[0] == classes[1] else "mixed/oblique"
            return {"classification": category, "product_type": kind, "source": p.get("source"),
                    "code": p.get("code"), "preferred_weight": p.get("preferredWeight"),
                    "updated_ms": p.get("updateTime"), "nodal_plane_rakes_deg": rakes,
                    "planes": [{k: props.get(f"nodal-plane-{n}-{k}") for k in ("strike", "dip", "rake")} for n in (1, 2)],
                    "note": "Descriptive two-plane rake rule, not identification of the actual fault plane or a quality-screened mechanism."}
    return {"classification": "unknown", "reason": "No usable two-plane rake parameters in available focal-mechanism/moment-tensor products."}


async def detail(event_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", event_id):
        raise ValueError("Use a USGS event ID, e.g. ci40925991, not a URL.")
    if event_id not in details:
        raw = await fetch("/query", {"eventid": event_id, "format": "geojson"})
        if raw.get("type") != "Feature":
            raise ValueError("Event not found; use an ID returned by search_earthquakes.")
        details[event_id] = raw
    return details[event_id]


@mcp.tool()
async def get_event_details(event_id: str) -> dict:
    """Get one USGS event's preferred location/magnitude and rake classification.

    event_id example: ci40925991. Returns both nodal-plane rakes, source and
    product type. Prefers highest weighted usable focal mechanism, then tensor.
    Strike-slip: within 30 degrees of 0/180; reverse: 60..120;
    normal: -120..-60. Other or disagreeing plane classes are mixed/oblique.
    Missing two-plane data is unknown; never infer mechanism from location.
    """
    raw = await detail(event_id)
    return event_row(raw) | {"mechanism": mechanism(raw)}


@mcp.tool()
async def summarize_mechanisms(catalog_id: str) -> dict:
    """Classify all events in a session catalog, reporting coverage and failures.

    Uses the documented two-plane rake rule in get_event_details, not USGS's
    event type (earthquake/explosion). Returns counts, fractions of all events
    and of events with usable mechanisms, plus a full per-event result path.
    Missing mechanisms and network failures are separate. Up to 500 catalog
    events; narrow search if larger. At most four concurrent USGS calls and
    a 240-second overall deadline. Configure host tool timeout >=250 seconds.
    """
    data = catalog(catalog_id)
    if len(data["events"]) > 500:
        raise ValueError("Mechanism scan supports <=500 events; narrow the catalog first.")
    semaphore = asyncio.Semaphore(4)

    async def one(row):
        if not any(k in row["products"] for k in ("focal-mechanism", "moment-tensor")):
            return {"id": row["id"], "classification": "unknown", "reason": "No mechanism product advertised."}
        async with semaphore:
            try:
                return {"id": row["id"], **mechanism(await detail(row["id"]))}
            except (RuntimeError, ValueError):
                return {"id": row["id"], "classification": "fetch_failed", "reason": "USGS detail unavailable; retry."}

    try:
        async with asyncio.timeout(240):
            results = await asyncio.gather(*(one(row) for row in data["events"]))
    except TimeoutError:
        raise RuntimeError("Mechanism scan timed out; narrow the query and retry. No partial statistics reported.") from None
    counts = Counter(r["classification"] for r in results)
    n = len(results)
    usable = n - counts["unknown"] - counts["fetch_failed"]
    categories = ("strike-slip", "reverse", "normal", "mixed/oblique", "unknown", "fetch_failed")
    result = {"catalog_id": catalog_id, "retrieved_utc": datetime.now(timezone.utc).isoformat(), "total_events": n, "usable_mechanisms": usable,
              "coverage_fraction": usable / n if n else None,
              "counts": {k: counts[k] for k in categories},
              "fractions_all": {k: counts[k] / n if n else None for k in categories},
              "fractions_usable": {k: counts[k] / usable if usable else None for k in categories[:4]},
              "limitations": "Selected two-plane rake classification; no mechanism quality filtering. Coverage is not representative by assumption. Reverse does not separately identify low-angle thrusts."}
    path = save(f"mechanisms-{catalog_id}.json", {**result, "events": results})
    return result | {"results_path": path}


def estimate_b(rows, mc, bin_width, mag_type):
    if not math.isfinite(mc) or not math.isfinite(bin_width) or not 0 <= bin_width <= 0.5:
        raise ValueError("Use finite Mc and magnitude_bin_width between 0 and 0.5.")
    selected = [r for r in rows if r["magnitude"] is not None and r["magnitude"] >= mc and (not mag_type or r["magnitude_type"] == mag_type)]
    magnitudes = [r["magnitude"] for r in selected]
    n = len(magnitudes)
    warnings = ["Mc is user-specified, not a completeness estimate. No declustering or magnitude homogenization was performed.",
                "Uncertainty is an approximate 1-sigma sampling error, excluding Mc, scale, and measurement uncertainty; clustered events violate independence."]
    types = dict(Counter(r["magnitude_type"] for r in selected))
    if mag_type:
        warnings.append("Filtering preferred magnitude types can introduce magnitude-dependent selection. This subset is not a complete homogeneous-scale catalog; retrieve alternate magnitudes and validate completeness before scientific interpretation.")
    if len(types) > 1:
        warnings.append("Mixed magnitude types: pooled b is exploratory. Use magnitude_type to select one scale.")
    if n < 50:
        warnings.append("Fewer than 50 events: small-sample estimate; interpret cautiously.")
    if bin_width and any(abs((m - mc) / bin_width - round((m - mc) / bin_width)) > 1e-5 for m in magnitudes):
        raise ValueError("Magnitudes are not on the requested bin grid relative to Mc. Use bin_width=0 for unrounded values; do not silently rebin.")
    if n < 10 or len(set(magnitudes)) < 2:
        return {"n": n, "mc": mc, "b": None, "reason": "Need >=10 events and at least two distinct magnitudes.", "warnings": warnings, "magnitude_types": types}
    mean = statistics.mean(magnitudes)
    denominator = mean - (mc - bin_width / 2)
    if denominator <= 0:
        raise ValueError("Degenerate magnitude range; choose a valid Mc/sample.")
    b = math.log10(math.e) / denominator
    sigma = math.log(10) * b * b * math.sqrt(sum((m - mean) ** 2 for m in magnitudes) / (n * (n - 1)))
    if max(magnitudes) - mc < 2:
        warnings.append("Observed magnitude span <2: inspect the frequency-magnitude distribution and unbounded GR assumption.")
    return {"n": n, "mc": mc, "mc_validated": False, "magnitude_bin_width": bin_width,
            "magnitude_type_filter": mag_type or "all", "magnitude_types": types,
            "mean_magnitude": mean, "max_magnitude": max(magnitudes), "b": b, "sigma_b_approx_1": sigma,
            "method": "Aki-Utsu MLE; optional half-bin correction", "formula": "b=log10(e)/(mean(M)-Mc+deltaM/2)",
            "uncertainty_method": "Shi-Bolt approximate standard error", "warnings": warnings}


@mcp.tool()
def calculate_b_value(catalog_id: str, mc: float = 3.0, magnitude_bin_width: float = 0,
                      magnitude_type: str = "") -> dict:
    """Estimate Gutenberg-Richter b for M>=Mc in an existing session catalog.

    Mc is user-specified (example 3.0), NOT proven completeness. It must be at
    least the catalog query cutoff. magnitude_bin_width=0 uses unrounded
    preferred magnitudes; positive deltaM requires all selected values on a
    grid relative to Mc and applies a half-bin correction, without rebinning.
    magnitude_type example 'ml' selects a single reported scale; empty pools
    all types with a warning. Reports sample size and approximate Shi-Bolt
    1-sigma error; <10 events or constant magnitudes produce no estimate.
    Uses all qualifying events, regardless of mechanism availability.
    """
    data = catalog(catalog_id)
    if mc < data["query"]["minmagnitude"]:
        raise ValueError("Mc is below the downloaded cutoff; rerun search_earthquakes with min_magnitude<=Mc.")
    result = {"catalog_id": catalog_id, **estimate_b(data["events"], mc, magnitude_bin_width, magnitude_type)}
    suffix = hashlib.sha256(json.dumps([mc, magnitude_bin_width, magnitude_type]).encode()).hexdigest()[:8]
    path = save(f"b-value-{catalog_id}-{suffix}.json", result)
    return result | {"results_path": path}


if __name__ == "__main__":
    mcp.run()
