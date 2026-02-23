import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BlogRevivalBot/1.0)"
}

# Module-level cache (used as fallback when session_state unavailable)
_cache: dict = {}


def _parse_sitemap_xml(xml_content: str, base_domain: str, depth: int = 0) -> list[dict]:
    """Parse a single sitemap XML and return list of page dicts."""
    if depth > 3:
        return []

    pages = []
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return []

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    # Sitemap index - recurse into child sitemaps
    if "sitemapindex" in root.tag:
        for sitemap_elem in root.findall(f"{ns}sitemap"):
            loc = sitemap_elem.find(f"{ns}loc")
            if loc is not None and loc.text:
                child_pages = _fetch_and_parse(loc.text.strip(), base_domain, depth + 1)
                pages.extend(child_pages)
    else:
        # Regular URL sitemap
        for url_elem in root.findall(f"{ns}url"):
            loc = url_elem.find(f"{ns}loc")
            if loc is None or not loc.text:
                continue
            page_url = loc.text.strip()
            path = urlparse(page_url).path.rstrip("/") or "/"
            slug = path if path.startswith("/") else "/" + path
            # Build a readable title from the slug
            raw = slug.split("/")[-1].replace("-", " ").replace("_", " ").strip()
            title = raw.title() if raw else slug
            pages.append({"url": page_url, "slug": slug, "title": title})

    return pages


def _fetch_and_parse(sitemap_url: str, base_domain: str, depth: int = 0) -> list[dict]:
    """Fetch a sitemap URL and parse it."""
    try:
        resp = requests.get(sitemap_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return _parse_sitemap_xml(resp.text, base_domain, depth)
    except Exception:
        return []


def get_site_pages(domain: str, session_state=None) -> list[dict]:
    """
    Discover all pages from a site's sitemap.
    Checks robots.txt for sitemap location, then falls back to common paths.
    Results are cached for the session.
    """
    # Normalize domain
    if not domain.startswith("http"):
        domain = "https://" + domain
    domain = domain.rstrip("/")

    cache_key = f"sitemap_{domain}"

    # Check Streamlit session_state cache
    if session_state is not None and cache_key in session_state:
        return session_state[cache_key]

    # Check module-level cache
    if cache_key in _cache:
        return _cache[cache_key]

    pages = []
    sitemap_candidates = []

    # Check robots.txt first for declared sitemap
    try:
        robots_resp = requests.get(f"{domain}/robots.txt", headers=HEADERS, timeout=10)
        if robots_resp.status_code == 200:
            for line in robots_resp.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    declared = line.split(":", 1)[1].strip()
                    sitemap_candidates.append(declared)
    except Exception:
        pass

    # Add common fallback locations
    sitemap_candidates.extend([
        f"{domain}/sitemap.xml",
        f"{domain}/sitemap_index.xml",
        f"{domain}/sitemap-index.xml",
        f"{domain}/wp-sitemap.xml",
    ])

    for sitemap_url in sitemap_candidates:
        found = _fetch_and_parse(sitemap_url, domain)
        if found:
            pages = found
            break

    # Store in both caches
    _cache[cache_key] = pages
    if session_state is not None:
        session_state[cache_key] = pages

    return pages
