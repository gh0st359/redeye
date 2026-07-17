"""People-centric OSINT: username presence, email intelligence, GitHub, breach data."""
from __future__ import annotations

import concurrent.futures
import hashlib
import re

import dns.resolver

from ..config import Config
from .base import ToolRegistry, ToolResult
from . import httpkit

# url patterns probed for username existence. {u} is replaced with the handle.
USERNAME_PLATFORMS = {
    "GitHub": "https://github.com/{u}",
    "GitLab": "https://gitlab.com/{u}",
    "Reddit": "https://www.reddit.com/user/{u}",
    "X/Twitter": "https://x.com/{u}",
    "Instagram": "https://www.instagram.com/{u}/",
    "TikTok": "https://www.tiktok.com/@{u}",
    "YouTube": "https://www.youtube.com/@{u}",
    "Medium": "https://medium.com/@{u}",
    "Pinterest": "https://www.pinterest.com/{u}/",
    "Twitch": "https://www.twitch.tv/{u}",
    "Steam": "https://steamcommunity.com/id/{u}",
    "Keybase": "https://keybase.io/{u}",
    "Mastodon": "https://mastodon.social/@{u}",
    "Bluesky": "https://bsky.app/profile/{u}.bsky.social",
    "DeviantArt": "https://www.deviantart.com/{u}",
    "Flickr": "https://www.flickr.com/people/{u}",
    "SoundCloud": "https://soundcloud.com/{u}",
    "Spotify": "https://open.spotify.com/user/{u}",
    "HackerNews": "https://news.ycombinator.com/user?id={u}",
    "StackOverflow": "https://stackoverflow.com/users?tab=accounts&search={u}",
    "Docker Hub": "https://hub.docker.com/u/{u}",
    "PyPI": "https://pypi.org/user/{u}/",
    "npm": "https://www.npmjs.com/~{u}",
    "Telegram": "https://t.me/{u}",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
    "yopmail.com", "throwawaymail.com", "sharklasers.com", "trashmail.com",
    "getnada.com", "dispostable.com", "temp-mail.org", "fakeinbox.com",
}


def register(registry: ToolRegistry, cfg: Config) -> None:

    @registry.tool(
        name="username_search",
        description=(
            "Check where a username/handle exists across ~25 major platforms (GitHub, Reddit, "
            "X, Instagram, Keybase, Telegram, ...). Status-code heuristic; treat hits as leads "
            "to verify, not proof."
        ),
        parameters={
            "type": "object",
            "properties": {"username": {"type": "string", "description": "Handle to check"}},
            "required": ["username"],
        },
        timeout=60.0,
    )
    def username_search(username: str) -> ToolResult:
        username = username.strip().lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,39}", username):
            return ToolResult.error(f"{username!r} contains characters invalid for most platforms")

        def probe(item: tuple[str, str]) -> tuple[str, str, int | None]:
            name, pattern = item
            url = pattern.format(u=username)
            try:
                with httpkit.client(timeout=12) as c:
                    r = c.get(url)
                return name, url, r.status_code
            except Exception:
                return name, url, None

        found, maybe = [], []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for name, url, status in pool.map(probe, USERNAME_PLATFORMS.items()):
                if status is not None and status < 400:
                    found.append((name, url, status))
                elif status in (401, 403, 429):
                    maybe.append((name, url, status))
        lines = [f"Username presence check for '{username}':"]
        if found:
            lines.append(f"  EXISTS ({len(found)}):")
            lines += [f"    [{name}] {url} (HTTP {s})" for name, url, s in found]
        if maybe:
            lines.append("  BLOCKED/RATE-LIMITED (verify manually):")
            lines += [f"    [{name}] {url} (HTTP {s})" for name, url, s in maybe]
        if not found and not maybe:
            lines.append("  No matches found on any checked platform.")
        return ToolResult(ok=True, content="\n".join(lines),
                          data={"found": len(found), "username": username})

    @registry.tool(
        name="gravatar_lookup",
        description=(
            "Look up the Gravatar profile for an email address — often reveals display name, "
            "bio, location, and linked accounts (WordPress, GitHub, social profiles)."
        ),
        parameters={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address"}},
            "required": ["email"],
        },
    )
    def gravatar_lookup(email: str) -> ToolResult:
        email = email.strip().lower()
        digest = hashlib.md5(email.encode()).hexdigest()  # noqa: S324 — gravatar requires md5
        status, data = httpkit.get_json(f"https://www.gravatar.com/{digest}.json")
        if status == 404:
            return ToolResult(ok=True, content=f"No Gravatar profile for {email}.")
        if status != 200 or not isinstance(data, dict):
            return ToolResult.error(f"Gravatar returned HTTP {status}")
        entries = data.get("entry", [])
        if not entries:
            return ToolResult(ok=True, content=f"No Gravatar profile for {email}.")
        e = entries[0]
        lines = [f"Gravatar profile for {email}:"]
        for key, label in (("displayName", "name"), ("aboutMe", "bio"),
                           ("currentLocation", "location"), ("profileUrl", "profile")):
            if e.get(key):
                lines.append(f"  {label}: {e[key]}")
        for acc in e.get("accounts", []) or []:
            lines.append(f"  linked [{acc.get('shortname', '?')}]: {acc.get('url', '?')}")
        for u in e.get("urls", []) or []:
            lines.append(f"  url: {u.get('value', '?')}")
        lines.append(f"  avatar: https://www.gravatar.com/avatar/{digest}?s=400")
        return ToolResult(ok=True, content="\n".join(lines))

    @registry.tool(
        name="email_intel",
        description=(
            "Full email address assessment: syntax, disposable-provider check, MX records of "
            "the domain, Gravatar presence, and (if HIBP_API_KEY set) known public breaches."
        ),
        parameters={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address"}},
            "required": ["email"],
        },
    )
    def email_intel(email: str) -> ToolResult:
        email = email.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return ToolResult.error(f"{email!r} is not a valid email address")
        local, domain = email.rsplit("@", 1)
        lines = [f"Email assessment: {email}"]
        lines.append(f"  disposable provider: {'YES' if domain in DISPOSABLE_DOMAINS else 'no'}")
        try:
            mx = dns.resolver.resolve(domain, "MX", lifetime=8)
            lines.append(f"  MX: {', '.join(str(r.exchange).rstrip('.') for r in mx)}")
        except Exception:
            lines.append("  MX: none found (domain may not accept mail)")
        digest = hashlib.md5(email.encode()).hexdigest()  # noqa: S324
        try:
            with httpkit.client(api=True, timeout=12) as c:
                r = c.get(f"https://www.gravatar.com/{digest}.json")
            lines.append(f"  gravatar: {'profile exists' if r.status_code == 200 else 'no profile'}")
        except Exception:
            lines.append("  gravatar: check failed")
        if cfg.hibp_api_key:
            try:
                with httpkit.client(api=True, timeout=20) as c:
                    r = c.get(
                        f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}",
                        params={"truncateResponse": "false"},
                        headers={"hibp-api-key": cfg.hibp_api_key},
                    )
                if r.status_code == 200:
                    breaches = r.json()
                    lines.append(f"  breaches: {len(breaches)} known breach(es):")
                    for b in breaches[:15]:
                        lines.append(
                            f"    - {b.get('Name', '?')} ({b.get('BreachDate', '?')}): "
                            f"{', '.join(b.get('DataClasses', [])[:6])}"
                        )
                elif r.status_code == 404:
                    lines.append("  breaches: none found (HIBP)")
                else:
                    lines.append(f"  breaches: HIBP returned HTTP {r.status_code}")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"  breaches: HIBP check failed ({exc})")
        else:
            lines.append("  breaches: set HIBP_API_KEY to enable Have I Been Pwned lookups")
        return ToolResult(ok=True, content="\n".join(lines))

    @registry.tool(
        name="github_user",
        description=(
            "Pull a GitHub user's public profile and their repos: name, bio, company, "
            "location, blog, email if public, top repositories by recent push."
        ),
        parameters={
            "type": "object",
            "properties": {"username": {"type": "string", "description": "GitHub login"}},
            "required": ["username"],
        },
    )
    def github_user(username: str) -> ToolResult:
        headers = {"Authorization": f"Bearer {cfg.github_token}"} if cfg.github_token else None
        status, data = httpkit.get_json(f"https://api.github.com/users/{username}", headers=headers)
        if status != 200 or not isinstance(data, dict):
            return ToolResult.error(f"GitHub API returned HTTP {status} for {username}")
        lines = [f"GitHub user: {username}"]
        for k in ("name", "company", "blog", "location", "email", "bio", "twitter_username"):
            if data.get(k):
                lines.append(f"  {k}: {data[k]}")
        lines.append(
            f"  repos: {data.get('public_repos', 0)} | followers: {data.get('followers', 0)} "
            f"| created: {data.get('created_at', '?')}"
        )
        rstatus, repos = httpkit.get_json(
            f"https://api.github.com/users/{username}/repos",
            params={"sort": "pushed", "per_page": 10},
            headers=headers,
        )
        if rstatus == 200 and isinstance(repos, list):
            lines.append("  recent repos:")
            for repo in repos[:10]:
                lines.append(
                    f"    - {repo.get('name', '?')} ({repo.get('language') or '?'}, "
                    f"★{repo.get('stargazers_count', 0)}, pushed {repo.get('pushed_at', '?')[:10]})"
                )
        return ToolResult(ok=True, content="\n".join(lines))

    @registry.tool(
        name="github_search",
        description=(
            "Search GitHub code/commits/issues/users — powerful for finding leaked emails, "
            "config files, API keys mentioned with a domain or name. Example queries: "
            "'@example.com in:file', 'filename:.env example', 'user:someone committer-email'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "GitHub search query"},
                "kind": {
                    "type": "string",
                    "enum": ["repositories", "code", "commits", "issues", "users"],
                    "description": "Search type (default repositories)",
                },
            },
            "required": ["query"],
        },
    )
    def github_search(query: str, kind: str = "repositories") -> ToolResult:
        kind = kind if kind in ("repositories", "code", "commits", "issues", "users") else "repositories"
        headers = {"Authorization": f"Bearer {cfg.github_token}"} if cfg.github_token else None
        if kind == "code" and not cfg.github_token:
            return ToolResult.error(
                "GitHub code search requires GITHUB_TOKEN (any classic PAT). "
                "Add it to ~/.redeye/config.toml or the environment."
            )
        status, data = httpkit.get_json(
            f"https://api.github.com/search/{kind}",
            params={"q": query, "per_page": 10},
            headers=headers,
        )
        if status != 200 or not isinstance(data, dict):
            return ToolResult.error(f"GitHub search returned HTTP {status}: {str(data)[:200]}")
        items = data.get("items", [])
        if not items:
            return ToolResult(ok=True, content=f"No GitHub {kind} results for: {query}")
        lines = [f"GitHub {kind} search: {query} ({data.get('total_count', '?')} total, showing {len(items)}):"]
        for it in items[:10]:
            if kind == "repositories":
                lines.append(f"  - {it.get('full_name', '?')} ★{it.get('stargazers_count', 0)} — {it.get('description') or ''} {it.get('html_url', '')}")
            elif kind == "users":
                lines.append(f"  - {it.get('login', '?')} {it.get('html_url', '')}")
            elif kind == "code":
                lines.append(f"  - {it.get('repository', {}).get('full_name', '?')}: {it.get('path', '?')} {it.get('html_url', '')}")
            elif kind == "commits":
                msg = (it.get("commit", {}).get("message", "") or "").split("\n")[0][:100]
                lines.append(f"  - {it.get('repository', {}).get('full_name', '?')}: {msg} {it.get('html_url', '')}")
            else:
                lines.append(f"  - {it.get('title', '?')} {it.get('html_url', '')}")
        return ToolResult(ok=True, content="\n".join(lines))
