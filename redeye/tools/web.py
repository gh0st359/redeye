"""Web OSINT tools: search, page fetch, archive, passive scan indexes."""
from __future__ import annotations

from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ..config import Config
from .base import ToolRegistry, ToolResult
from . import httpkit


def register(registry: ToolRegistry, cfg: Config) -> None:

    @registry.tool(
        name="web_search",
        description=(
            "Search the public web. Uses Brave if an API key is configured, then Tavily, "
            "otherwise DuckDuckGo. Returns titles, URLs and snippets. Use targeted queries: "
            'quoted phrases, site: filters, filetype:, inurl:.'
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (operators supported)"},
                "count": {"type": "integer", "description": "Max results (default 8, max 20)"},
            },
            "required": ["query"],
        },
    )
    def web_search(query: str, count: int = 8) -> ToolResult:
        count = max(1, min(int(count or 8), 20))

        if cfg.brave_api_key:
            try:
                status, data = httpkit.get_json(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": count},
                    headers={"X-Subscription-Token": cfg.brave_api_key},
                )
                if status == 200 and isinstance(data, dict):
                    results = [
                        (r.get("title", ""), r.get("url", ""), r.get("description", ""))
                        for r in (data.get("web", {}) or {}).get("results", [])
                    ]
                    if results:
                        return _format_results(query, results, "brave")
            except Exception:
                pass  # fall through to next engine

        if cfg.tavily_api_key:
            try:
                with httpkit.client(api=True) as c:
                    r = c.post(
                        "https://api.tavily.com/search",
                        json={"api_key": cfg.tavily_api_key, "query": query, "max_results": count},
                    )
                    if r.status_code == 200:
                        results = [
                            (x.get("title", ""), x.get("url", ""), x.get("content", ""))
                            for x in r.json().get("results", [])
                        ]
                        if results:
                            return _format_results(query, results, "tavily")
            except Exception:
                pass

        # DuckDuckGo HTML fallback (no key required)
        last_err = None
        for url, method in (
            ("https://html.duckduckgo.com/html/", "get"),
            ("https://lite.duckduckgo.com/lite/", "post"),
        ):
            try:
                with httpkit.client() as c:
                    if method == "get":
                        resp = c.get(url, params={"q": query})
                    else:
                        resp = c.post(url, data={"q": query})
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}"
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                results = []
                for a in soup.select("a.result__a") or soup.select("a.result-link"):
                    href = a.get("href", "")
                    title = a.get_text(" ", strip=True)
                    if href and title:
                        results.append((title, href, ""))
                    if len(results) >= count:
                        break
                if results:
                    return _format_results(query, results, "duckduckgo")
                last_err = "no parseable results (possible rate limit)"
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
        return ToolResult.error(f"all search backends failed for {query!r} (last: {last_err}). "
                                "Set BRAVE_API_KEY or TAVILY_API_KEY for reliable search.")

    @registry.tool(
        name="fetch_url",
        description=(
            "Fetch a public web page and return its readable text content (stripped of "
            "navigation/scripts). Use to read articles, profiles, documents found via search."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Fully-qualified URL to fetch"},
                "max_chars": {"type": "integer", "description": "Cap on returned text (default 6000)"},
            },
            "required": ["url"],
        },
    )
    def fetch_url(url: str, max_chars: int = 6000) -> ToolResult:
        max_chars = max(500, min(int(max_chars or 6000), 20000))
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        with httpkit.client(timeout=30) as c:
            resp = c.get(url)
        ctype = resp.headers.get("content-type", "")
        if resp.status_code >= 400:
            return ToolResult.error(f"HTTP {resp.status_code} for {url}")
        if "text" not in ctype and "html" not in ctype and "json" not in ctype:
            return ToolResult(
                ok=True,
                content=f"{url} returned content-type {ctype!r} ({len(resp.content)} bytes); "
                        "not text — use extract_metadata on a downloaded copy if needed.",
            )
        if "json" in ctype:
            text = resp.text
        else:
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
                tag.decompose()
            text = soup.get_text("\n", strip=True)
        title = ""
        try:
            title = BeautifulSoup(resp.text, "html.parser").title.string or ""
        except Exception:
            pass
        out = f"# {title.strip()}\n{url}\n\n{text[:max_chars]}"
        return ToolResult(ok=True, content=out, truncated=len(text) > max_chars)

    @registry.tool(
        name="wayback_snapshots",
        description=(
            "List archived snapshots of a URL or domain from the Wayback Machine CDX index. "
            "Great for finding deleted pages, old employee lists, historical site content."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL or domain, e.g. example.com/*"},
                "limit": {"type": "integer", "description": "Max snapshots (default 15)"},
            },
            "required": ["url"],
        },
    )
    def wayback_snapshots(url: str, limit: int = 15) -> ToolResult:
        limit = max(1, min(int(limit or 15), 50))
        status, data = httpkit.get_json(
            "https://web.archive.org/cdx/search/cdx",
            params={
                "url": url,
                "output": "json",
                "limit": limit,
                "collapse": "digest",
                "filter": "statuscode:200",
            },
            timeout=40,
        )
        if status != 200 or not isinstance(data, list) or len(data) < 2:
            return ToolResult(ok=True, content=f"No Wayback snapshots found for {url} (HTTP {status}).")
        rows = data[1:]
        lines = [f"{len(rows)} snapshot(s) for {url} (most recent last):"]
        for row in rows:
            ts, original, statuscode = row[1], row[2], row[4]
            lines.append(f"- {ts}  [{statuscode}]  https://web.archive.org/web/{ts}/{original}")
        return ToolResult(ok=True, content="\n".join(lines))

    @registry.tool(
        name="urlscan_search",
        description=(
            "Query urlscan.io's passive scan index for a domain — recent scans, observed "
            "IPs, ASNs, page titles, linked domains, technologies. Fully passive."
        ),
        parameters={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain to search, e.g. example.com"},
            },
            "required": ["domain"],
        },
    )
    def urlscan_search(domain: str) -> ToolResult:
        status, data = httpkit.get_json(
            "https://urlscan.io/api/v1/search/",
            params={"q": f"domain:{domain}", "size": 20},
        )
        if status != 200 or not isinstance(data, dict):
            return ToolResult.error(f"urlscan.io returned HTTP {status}")
        results = data.get("results", [])
        if not results:
            return ToolResult(ok=True, content=f"urlscan.io has no recorded scans for {domain}.")
        lines = [f"urlscan.io: {len(results)} recent scan(s) mentioning {domain}:"]
        for r in results:
            page = r.get("page", {})
            lines.append(
                f"- {r.get('task', {}).get('time', '?')} | {page.get('url', '?')} | "
                f"ip={page.get('ip', '?')} asn={page.get('asn', '?')} "
                f"server={page.get('server', '?')} | scan: {r.get('result', '')}"
            )
        return ToolResult(ok=True, content="\n".join(lines))


def _format_results(query: str, results: list[tuple[str, str, str]], engine: str) -> ToolResult:
    lines = [f"Search results for: {query}  (engine: {engine})"]
    for i, (title, url, snippet) in enumerate(results, 1):
        lines.append(f"{i}. {title}\n   {url}")
        if snippet:
            lines.append(f"   {snippet[:300]}")
    return ToolResult(ok=True, content="\n".join(lines), data={"engine": engine})
