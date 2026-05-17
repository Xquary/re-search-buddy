import asyncio, os, httpx, dotenv

dotenv.load_dotenv()
api_key = os.environ.get("SCOPUS_API_KEY", "")

query = (
    '(ABM OR "agent-based" OR "multi-agent system" OR MAS)'
    ' AND (energy OR "energy market" OR "energy transition"'
    ' OR "energy behaviour" OR "energy behavior" OR "energy system")'
    ' AND (SUBJAREA(ENER) OR SUBJAREA(ENVI) OR SUBJAREA(ENGI)'
    ' OR SUBJAREA(COMP) OR SUBJAREA(DECI) OR SUBJAREA(MATH))'
    ' AND SRCTYPE(j)'
)

async def main():
    async with httpx.AsyncClient(
        headers={"X-ELS-APIKey": api_key, "Accept": "application/json"},
        timeout=30,
    ) as c:
        r = await c.get(
            "https://api.elsevier.com/content/search/scopus",
            params={"query": query, "count": 1, "start": 0, "view": "STANDARD", "date": "2016-2099"},
        )
        d = r.json()
        print("Layer 2 + all subj + journal")
        print(f"Total: {d.get('search-results', {}).get('opensearch:totalResults', '?')}")

asyncio.run(main())
