# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2,<3", "httpx>=0.28,<1"]
# ///
import math
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mcp import Client
import server


def row(mag, depth=5, kind="ml"):
    return {"id": str(mag), "magnitude": mag, "magnitude_type": kind, "depth_km": depth,
            "time_utc": "2024-01-01T00:00:00+00:00", "products": ""}


class ScienceTests(unittest.TestCase):
    def test_known_exponential_population(self):
        rng = random.Random(12)
        rows = [row(3 + rng.expovariate(math.log(10))) for _ in range(20000)]
        result = server.estimate_b(rows, 3, 0, "")
        self.assertAlmostEqual(result["b"], 1, delta=.025)
        self.assertGreater(result["sigma_b_approx_1"], 0)

    def test_bin_correction_and_bad_grid(self):
        rows = [row(3 + k / 10) for k in range(20)]
        result = server.estimate_b(rows, 3, .1, "")
        self.assertAlmostEqual(result["b"], math.log10(math.e))
        with self.assertRaises(ValueError):
            server.estimate_b(rows + [row(3.057)], 3, .1, "")

    def test_cutoff_type_filter_and_small_sample(self):
        rows = [row(2.9)] * 20 + [row(3.2, kind="mw")] * 20 + [row(3.1 + k / 100) for k in range(20)]
        result = server.estimate_b(rows, 3, 0, "ml")
        self.assertEqual(result["n"], 20)
        self.assertEqual(result["magnitude_types"], {"ml": 20})
        self.assertIsNone(server.estimate_b([row(3.1)] * 10, 3, 0, "")["b"])
        self.assertIsNone(server.estimate_b(rows[:2], 3, 0, "")["b"])

    def test_depth_boundaries_and_missing(self):
        server.catalogs["test"] = {"events": [row(3, d) for d in (-1, 0, 9.9, 10, None)]}
        summary = server.summarize_catalog("test", 10)
        self.assertEqual(summary["depth_missing"], 1)
        self.assertEqual([b["count"] for b in summary["depth_bins"]], [1, 2, 1])

    def test_mechanism_ambiguity_and_product_preference(self):
        def product(r1, r2, weight):
            return {"preferredWeight": weight, "properties": {"nodal-plane-1-rake": r1, "nodal-plane-2-rake": r2}}
        event = {"properties": {"products": {"focal-mechanism": [product(90, 90, 1), product(5, 175, 10)]}}}
        self.assertEqual(server.mechanism(event)["classification"], "strike-slip")
        event["properties"]["products"]["focal-mechanism"] = [product(90, 0, 1)]
        self.assertEqual(server.mechanism(event)["classification"], "mixed/oblique")
        self.assertEqual(server.mechanism({})["classification"], "unknown")
        self.assertEqual(server.rake_class(-90), "normal")
        self.assertEqual(server.rake_class(90), "reverse")


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_result_files_deleted_on_session_close(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server, 'BASE_OUTPUT', Path(tmp)):
            async with Client(server.mcp):
                path = Path(server.save('catalog-test.json', {'public':'data'}))
                session = path.parent
                self.assertTrue(path.exists())
            self.assertFalse(session.exists())
            self.assertIsNone(server.OUTPUT)
            self.assertFalse(server.catalogs)

    async def test_stale_cleanup_preserves_active_or_unknown_folders(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ('stale', 'active', 'unknown'):
                (base/f'session-{name}').mkdir()
            (base/'session-stale/owner.json').write_text(json.dumps({'pid':99999999}))
            (base/'session-active/owner.json').write_text(json.dumps({'pid':12345}))
            def check(pid, signal):
                if pid == 99999999:
                    raise ProcessLookupError()
            with patch.object(server.os, 'kill', side_effect=check):
                server.cleanup_stale_sessions(base)
            self.assertFalse((base/'session-stale').exists())
            self.assertTrue((base/'session-active').exists())
            self.assertTrue((base/'session-unknown').exists())

    async def test_unknown_catalog_returns_actionable_mcp_error(self):
        async with Client(server.mcp) as client:
            result = await client.call_tool('summarize_catalog', {'catalog_id':'nonexistent-id'})
            self.assertTrue(result.is_error)
            self.assertIn('Copy the exact catalog_id', result.content[0].text)

    async def test_mcp_discovery_and_real_dispatch(self):
        server.catalogs["protocol"] = {"events": [row(3.1 + k / 10) for k in range(20)], "query": {"minmagnitude": 3}}
        with patch.object(server, "save", return_value="/tmp/mock-result.json"):
            async with Client(server.mcp) as client:
                tools = await client.list_tools()
                self.assertEqual(len(tools.tools), 5)
                result = await client.call_tool("calculate_b_value", {"catalog_id": "protocol", "mc": 3})
                self.assertFalse(result.is_error)

    async def test_catalog_mismatch_refuses_partial_result(self):
        with patch.object(server, "fetch", AsyncMock(side_effect=[{"count": 5}, {"features": []}])):
            with self.assertRaises(RuntimeError):
                await server.search_earthquakes("2021-01-01", "2022-01-01")


if __name__ == "__main__":
    unittest.main()
