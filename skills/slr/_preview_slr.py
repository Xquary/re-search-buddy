"""Preview result counts for SLR query variants."""
import asyncio, os, httpx, dotenv
dotenv.load_dotenv()
api_key = os.environ.get("SCOPUS_API_KEY", "")

qA = '(ABM OR "agent-based" OR "multi-agent system" OR MAS)'
qB = ('(ABM OR "agent-based" OR "multi-agent system" OR MAS)'
      ' AND (energy OR "energy market" OR "energy transition"'
      ' OR "energy behaviour" OR "energy behavior" OR "energy system")'
      ' AND (SUBJAREA(ENER) OR SUBJAREA(ENVI) OR SUBJAREA(ENGI)'
      ' OR SUBJAREA(COMP) OR SUBJAREA(DECI) OR SUBJAREA(MATH))'
      ' AND SRCTYPE(j)')
qBprime = ('(ABM OR "agent-based" OR "multi-agent system" OR MAS)'
           ' AND ("energy market" OR "energy transition"'
           ' OR "energy behaviour" OR "energy behavior" OR "energy system")'
           ' AND (SUBJAREA(ENER) OR SUBJAREA(ENVI) OR SUBJAREA(ENGI)'
           ' OR SUBJAREA(COMP) OR SUBJAREA(DECI) OR SUBJAREA(MATH))'
           ' AND SRCTYPE(j)')
qC = ('(ABM OR "agent-based" OR "multi-agent system" OR MAS)'
      ' AND (SUBJAREA(ENER) OR SUBJAREA(ENVI) OR SUBJAREA(ENGI)'
      ' OR SUBJAREA(COMP) OR SUBJAREA(DECI) OR SUBJAREA(MATH))'
      ' AND SRCTYPE(j)')

async def count(client, query, label):
    r = await client.get(
        "https://api.elsevier.com/content/search/scopus",
        params={"query": query, "count": 1, "start": 0, "view": "STANDARD"},
    )
    d = r.json()
    total = d.get("search-results", {}).get("opensearch:totalResults", "?")
    print(f"  {label}: {total}")
    return total

async def main():
    async with httpx.AsyncClient(
        headers={"X-ELS-APIKey": api_key, "Accept": "application/json"},
        timeout=30,
    ) as c:
        print("No year filter:")
        print("=" * 60)
        await count(c, qA, "A) ABM-only (broad)")
        await count(c, qB, "B) ABM + energy + subj + journal")
        await count(c, qBprime, "B') ABM + energy-terms (no bare energy) + subj + journal")
        await count(c, qC, "C) ABM + subj + journal (no energy at all)")
        print()
        print("With date=2016-2099:")
        print("=" * 60)
        async with httpx.AsyncClient(
            headers={"X-ELS-APIKey": api_key, "Accept": "application/json"},
            timeout=30,
        ) as c2:
            for label, q in [
                ("A) ABM-only", qA),
                ("B) ABM+energy+subj+journal", qB),
                ("B') ABM+energy-terms+subj+journal", qBprime),
                ("C) ABM+subj+journal", qC),
            ]:
                r = await c2.get(
                    "https://api.elsevier.com/content/search/scopus",
                    params={"query": q, "count": 1, "start": 0, "view": "STANDARD", "date": "2016-2099"},
                )
                d = r.json()
                total = d.get("search-results", {}).get("opensearch:totalResults", "?")
                print(f"  {label}: {total}")

asyncio.run(main())
