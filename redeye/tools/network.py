"""Network & infrastructure OSINT: DNS, RDAP, certificate transparency, IP intel."""
from __future__ import annotations

import ipaddress

import dns.resolver
import dns.reversename

from ..config import Config
from .base import ToolRegistry, ToolResult
from . import httpkit


def register(registry: ToolRegistry, cfg: Config) -> None:

    @registry.tool(
        name="dns_records",
        description=(
            "Resolve DNS records for a domain: A, AAAA, MX, NS, TXT (SPF/DKIM/DMARC reveal "
            "mail providers and cloud services), CNAME, SOA, CAA."
        ),
        parameters={
            "type": "object",
            "properties": {"domain": {"type": "string", "description": "Domain name"}},
            "required": ["domain"],
        },
    )
    def dns_records(domain: str) -> ToolResult:
        domain = domain.strip().lower().removeprefix("http://").removeprefix("https://").split("/")[0]
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 8
        out: list[str] = [f"DNS records for {domain}:"]
        found = False
        for rtype in ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA"):
            try:
                answers = resolver.resolve(domain, rtype)
                found = True
                for r in answers:
                    out.append(f"  {rtype:6} {r.to_text()}")
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers,
                    dns.resolver.Timeout, dns.exception.DNSException):
                continue
        if not found:
            return ToolResult(ok=True, content=f"No DNS records resolved for {domain} (NXDOMAIN or no records).")
        return ToolResult(ok=True, content="\n".join(out))

    @registry.tool(
        name="rdap_lookup",
        description=(
            "Registration data (RDAP, the modern WHOIS) for a domain or IP address: registrar, "
            "creation/expiry dates, registrant organization when published, nameservers, "
            "network allocation owner, abuse contacts."
        ),
        parameters={
            "type": "object",
            "properties": {"target": {"type": "string", "description": "Domain or IP address"}},
            "required": ["target"],
        },
    )
    def rdap_lookup(target: str) -> ToolResult:
        target = target.strip().lower()
        try:
            ipaddress.ip_address(target)
            url = f"https://rdap.org/ip/{target}"
            kind = "ip"
        except ValueError:
            url = f"https://rdap.org/domain/{target}"
            kind = "domain"
        status, data = httpkit.get_json(url, timeout=30)
        if status != 200 or not isinstance(data, dict):
            return ToolResult.error(f"RDAP returned HTTP {status} for {target}")
        lines = [f"RDAP ({kind}) for {target}:"]
        if data.get("ldhName"):
            lines.append(f"  name: {data['ldhName']}")
        if data.get("handle"):
            lines.append(f"  handle: {data['handle']}")
        for ev in data.get("events", []) or []:
            lines.append(f"  {ev.get('eventAction', '?')}: {ev.get('eventDate', '?')}")
        for ent in data.get("entities", []) or []:
            roles = ",".join(ent.get("roles", []))
            vcard = ent.get("vcardArray", [None, []])[1]
            fields = {}
            for item in vcard:
                if isinstance(item, list) and len(item) >= 4:
                    fields.setdefault(item[0], item[3])
            desc = " | ".join(
                f"{k}={v}" for k, v in fields.items() if k in ("fn", "org", "email", "tel", "adr")
            )
            lines.append(f"  entity[{roles}]: {desc or ent.get('handle', '?')}")
        for ns in data.get("nameservers", []) or []:
            lines.append(f"  ns: {ns.get('ldhName', '?')}")
        if data.get("name"):
            lines.append(f"  network: {data.get('name')} ({data.get('startAddress', '')}-{data.get('endAddress', '')})")
        if data.get("country"):
            lines.append(f"  country: {data['country']}")
        if data.get("status"):
            lines.append(f"  status: {', '.join(data['status'])}")
        return ToolResult(ok=True, content="\n".join(lines))

    @registry.tool(
        name="crtsh_subdomains",
        description=(
            "Enumerate subdomains from Certificate Transparency logs (crt.sh). Reveals "
            "dev/staging/internal hosts, forgotten services, and infrastructure sprawl."
        ),
        parameters={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Apex domain, e.g. example.com"},
                "limit": {"type": "integer", "description": "Max names (default 100)"},
            },
            "required": ["domain"],
        },
    )
    def crtsh_subdomains(domain: str, limit: int = 100) -> ToolResult:
        limit = max(1, min(int(limit or 100), 500))
        status, data = httpkit.get_json(
            "https://crt.sh/", params={"q": f"%.{domain}", "output": "json"}, timeout=40
        )
        if status != 200 or not isinstance(data, list):
            return ToolResult.error(f"crt.sh returned HTTP {status} for {domain}")
        names: set[str] = set()
        for entry in data:
            for name in str(entry.get("name_value", "")).split("\n"):
                name = name.strip().lower().lstrip("*.")
                if name.endswith(domain.lower()):
                    names.add(name)
        if not names:
            return ToolResult(ok=True, content=f"No certificate-transparency entries for {domain}.")
        ordered = sorted(names)[:limit]
        lines = [f"{len(names)} unique name(s) in CT logs for {domain} (showing {len(ordered)}):"]
        lines += [f"  {n}" for n in ordered]
        return ToolResult(ok=True, content="\n".join(lines), data={"count": len(names)})

    @registry.tool(
        name="ip_intel",
        description=(
            "Geolocation, ASN, and hosting organization for an IP address, plus reverse DNS. "
            "Passively queries public IP intelligence APIs."
        ),
        parameters={
            "type": "object",
            "properties": {"ip": {"type": "string", "description": "IPv4/IPv6 address"}},
            "required": ["ip"],
        },
    )
    def ip_intel(ip: str) -> ToolResult:
        ip = ip.strip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return ToolResult.error(f"{ip!r} is not a valid IP address")
        lines = [f"IP intelligence for {ip}:"]
        # reverse DNS
        try:
            rev = dns.reversename.from_address(ip)
            answers = dns.resolver.resolve(rev, "PTR", lifetime=6)
            lines.append(f"  ptr: {', '.join(r.to_text().rstrip('.') for r in answers)}")
        except Exception:
            lines.append("  ptr: (none)")
        # geolocation / ASN
        try:
            status, data = httpkit.get_json(f"https://ipapi.co/{ip}/json/", timeout=15)
            if status == 200 and isinstance(data, dict) and not data.get("error"):
                lines.append(
                    f"  geo: {data.get('city', '?')}, {data.get('region', '?')}, "
                    f"{data.get('country_name', '?')} ({data.get('latitude', '?')}, {data.get('longitude', '?')})"
                )
                lines.append(f"  org: {data.get('org', '?')} | asn: {data.get('asn', '?')}")
                lines.append(f"  network: {data.get('network', '?')} | tz: {data.get('timezone', '?')}")
                return ToolResult(ok=True, content="\n".join(lines))
        except Exception:
            pass
        try:
            status, data = httpkit.get_json(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,regionName,city,lat,lon,isp,org,as,hosting,proxy"},
                timeout=15,
            )
            if status == 200 and isinstance(data, dict) and data.get("status") == "success":
                lines.append(
                    f"  geo: {data.get('city', '?')}, {data.get('regionName', '?')}, "
                    f"{data.get('country', '?')} ({data.get('lat', '?')}, {data.get('lon', '?')})"
                )
                lines.append(f"  isp: {data.get('isp', '?')} | org: {data.get('org', '?')} | {data.get('as', '?')}")
                flags = [k for k in ("hosting", "proxy") if data.get(k)]
                if flags:
                    lines.append(f"  flags: {', '.join(flags)}")
                return ToolResult(ok=True, content="\n".join(lines))
        except Exception:
            pass
        lines.append("  (geolocation providers unavailable; PTR/RDAP data above still valid)")
        return ToolResult(ok=True, content="\n".join(lines))

    @registry.tool(
        name="http_headers",
        description=(
            "Fetch the HTTP response headers, redirect chain, page title and server banner "
            "of a website. NOTE: this contacts the subject's infrastructure directly — a "
            "single ordinary GET request, visible in their logs."
        ),
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL or domain"}},
            "required": ["url"],
        },
        tier="active",
    )
    def http_headers(url: str) -> ToolResult:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        with httpkit.client(timeout=20) as c:
            resp = c.get(url)
        lines = [f"GET {url} -> HTTP {resp.status_code}"]
        if resp.history:
            lines.append("  redirects:")
            for h in resp.history:
                lines.append(f"    {h.status_code} {h.url} -> {h.headers.get('location', '?')}")
        lines.append("  headers:")
        for k, v in resp.headers.items():
            lines.append(f"    {k}: {v}")
        try:
            from bs4 import BeautifulSoup

            title = BeautifulSoup(resp.text, "html.parser").title
            if title and title.string:
                lines.append(f"  title: {title.string.strip()}")
        except Exception:
            pass
        return ToolResult(ok=True, content="\n".join(lines))
