# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2,<3", "httpx>=0.28,<1"]
# ///
import asyncio
import json
from pathlib import Path
from mcp import Client
from mcp.client.stdio import StdioServerParameters

SERVER = Path(__file__).resolve().with_name("server.py")

def unpack(result):
    if result.is_error:
        raise RuntimeError(str(result.content))
    data = result.structured_content
    return data.get('result', data) if data else json.loads(result.content[0].text)

async def main():
    params = StdioServerParameters(command='uv', args=['run','--script',str(SERVER)])
    async with Client(params) as client:
        report = {}
        report['tools'] = [t.name for t in (await client.list_tools()).tools]
        report['search'] = unpack(await client.call_tool('search_earthquakes', {'starttime':'2021-10-21','endtime':'2026-10-21','latitude':33.3,'longitude':-115.8,'radius_km':100,'min_magnitude':3.0}))
        cid = report['search']['catalog_id']
        print('Catalog count:', report['search']['count'], flush=True)
        report['depth'] = unpack(await client.call_tool('summarize_catalog', {'catalog_id':cid}))
        report['b_pooled'] = unpack(await client.call_tool('calculate_b_value', {'catalog_id':cid,'mc':3.0}))
        report['b_by_type'] = {}
        for kind in report['search']['magnitude_types']:
            report['b_by_type'][kind] = unpack(await client.call_tool('calculate_b_value', {'catalog_id':cid,'mc':3.0,'magnitude_type':kind}))
        report['event_example'] = unpack(await client.call_tool('get_event_details', {'event_id':'ci40925991'}))
        report['mechanisms'] = unpack(await client.call_tool('summarize_mechanisms', {'catalog_id':cid}, read_timeout_seconds=250))
        print(json.dumps({'count':report['search']['count'],'depth':report['depth']['depth_km'],'b_pooled':report['b_pooled'],'b_by_type':report['b_by_type'],'mechanisms':report['mechanisms'],'retention':'Temporary data files are deleted when this MCP session closes.'},indent=2),flush=True)

asyncio.run(main())
