"""
lead_finder.py — WebSearch + NPI Registry + BBB Lead Discovery
Multi-source parallel lead finding from cloud (no Playwright needed).
"""

import asyncio
import logging
import re
import time
from typing import List, Dict, Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"(?:\+1[\s.-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
WEBSITE_RE = re.compile(r"https?://[^\s\"'<>,]+")

HEADERS_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
]


async def _web_search(query: str, client: httpx.AsyncClient, num_results: int = 10) -> List[Dict]:
    """Search via multiple free search APIs with fallback."""
    results = []

    try:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "Accept-Encoding": "gzip"},
            params={"q": query, "count": num_results},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            for r in data.get("web", {}).get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("description", ""),
                })
    except Exception:
        pass

    if not results:
        try:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": HEADERS_LIST[0]},
                timeout=10,
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for item in soup.select(".result")[:num_results]:
                    title_el = item.select_one(".result__title a")
                    snippet_el = item.select_one(".result__snippet")
                    if title_el:
                        results.append({
                            "title": title_el.get_text(strip=True),
                            "url": title_el.get("href", ""),
                            "description": snippet_el.get_text(strip=True) if snippet_el else "",
                        })
        except Exception:
            pass

    return results


async def _search_businesses(niche: str, city: str, state: str, client: httpx.AsyncClient) -> List[Dict]:
    """Search for businesses using multiple queries."""
    queries = [
        f"{niche} contractor {city} {state} phone website",
        f"{niche} company {city} {state} owner contact",
        f"best {niche} {city} {state} reviews",
        f"{niche} service near {city} {state}",
        f"{niche} {city} {state} BBB verified",
    ]

    leads = []
    seen_names = set()

    for q in queries:
        try:
            results = await _web_search(q, client, num_results=10)
            for r in results:
                title = r["title"]
                desc = r["description"]
                url = r["url"]

                name = _extract_business_name(title, desc)
                if not name or name.lower() in seen_names:
                    continue
                seen_names.add(name.lower())

                phone = _extract_phone(desc) or _extract_phone(title)
                website = url if any(d in url for d in [".com", ".net", ".org", ".io"]) else ""
                email = _extract_email(desc)

                owner = _extract_owner_from_text(desc)

                leads.append({
                    "business_name": name,
                    "owner_name": owner,
                    "phone": phone,
                    "email": email,
                    "website": website,
                    "city": city,
                    "state": state,
                    "niche": niche,
                    "source": "websearch",
                })

            await asyncio.sleep(1.5)
        except Exception as e:
            logger.warning(f"Search error for '{q}': {e}")

    return leads


async def _search_npi(niche: str, city: str, state: str, client: httpx.AsyncClient) -> List[Dict]:
    """Search NPI Registry for medical/dental leads."""
    medical_niches = {"medical", "dental", "clinic", "doctor", "physician"}
    if not any(m in niche.lower() for m in medical_niches):
        return []

    leads = []
    try:
        resp = await client.get(
            "https://npiregistry.cms.hhs.gov/api/",
            params={
                "version": "2.1",
                "limit": 200,
                "skip": 0,
                "state": state.upper(),
                "enumeration_type": "NPI-1",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("results", []):
                basic = item.get("basic", {})
                addresses = item.get("addresses", [])
                practice_addr = None
                for addr in addresses:
                    if addr.get("address_purpose") == "LOCATION":
                        practice_addr = addr
                        break
                if not practice_addr and addresses:
                    practice_addr = addresses[0]

                if not practice_addr:
                    continue

                addr_city = practice_addr.get("city", "").strip()
                if city.lower() not in addr_city.lower():
                    continue

                name = basic.get("authorized_official_first_name", "") + " " + basic.get("authorized_official_last_name", "")
                name = name.strip()
                if not name:
                    org_name = basic.get("authorized_official_name_prefix", "")
                    name = org_name or basic.get("organization_name", "")

                phone = practice_addr.get("telephone_number", "")

                leads.append({
                    "business_name": basic.get("organization_name", name),
                    "owner_name": name,
                    "phone": phone,
                    "email": "",
                    "website": "",
                    "city": addr_city,
                    "state": state,
                    "niche": niche,
                    "source": "npi_registry",
                    "npi": item.get("number", ""),
                })

    except Exception as e:
        logger.warning(f"NPI search error: {e}")

    return leads


async def _search_bbb(niche: str, city: str, state: str, client: httpx.AsyncClient) -> List[Dict]:
    """Search BBB for verified businesses."""
    leads = []
    queries = [
        f"site:bbb.org {niche} {city} {state}",
        f"site:bbb.org {niche} contractor {city} {state}",
    ]

    for q in queries:
        try:
            results = await _web_search(q, client, num_results=10)
            for r in results:
                desc = r["description"]
                title = r["title"]

                name = _extract_business_name(title, desc)
                if not name:
                    continue

                phone = _extract_phone(desc) or _extract_phone(title)
                website = ""
                url_match = re.search(r"bbb\.org/[^/]+/[^/]+/(.+?)(?:\s|$)", r["url"])
                if url_match:
                    website = r["url"]

                leads.append({
                    "business_name": name,
                    "owner_name": "",
                    "phone": phone,
                    "email": "",
                    "website": website,
                    "city": city,
                    "state": state,
                    "niche": niche,
                    "source": "bbb",
                })

            await asyncio.sleep(1.5)
        except Exception as e:
            logger.warning(f"BBB search error: {e}")

    return leads


async def _find_owner_for_lead(lead: Dict, client: httpx.AsyncClient) -> str:
    """Try to find owner name for a lead that doesn't have one."""
    if lead.get("owner_name"):
        return lead["owner_name"]

    name = lead.get("business_name", "")
    city = lead.get("city", "")
    state = lead.get("state", "")
    website = lead.get("website", "")

    if website:
        try:
            about_urls = [
                website.rstrip("/") + "/about",
                website.rstrip("/") + "/about-us",
                website.rstrip("/") + "/team",
                website.rstrip("/") + "/contact",
            ]
            for about_url in about_urls[:2]:
                try:
                    resp = await client.get(about_url, headers={"User-Agent": HEADERS_LIST[0]}, timeout=8)
                    if resp.status_code == 200:
                        text = resp.text
                        owner = _extract_owner_from_html(text)
                        if owner:
                            return owner
                except Exception:
                    pass
        except Exception:
            pass

    try:
        query = f'"{name}" {city} {state} owner founder CEO president'
        results = await _web_search(query, client, num_results=5)
        for r in results:
            text = r["title"] + " " + r["description"]
            owner = _extract_owner_from_text(text)
            if owner:
                return owner
    except Exception:
        pass

    return ""


def _extract_business_name(title: str, desc: str) -> str:
    """Extract business name from search result title/description."""
    name = title.split(" - ")[0].split(" | ")[0].split(" – ")[0].strip()
    for suffix in [" - BBB", " | Yelp", " - Reviews", " - Home", " - Contact"]:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    if len(name) > 60:
        name = name[:60].strip()
    if not name or len(name) < 3:
        return ""
    skip_words = ["home", "about", "contact", "reviews", "services", "best", "top", "near", "search"]
    if name.lower().split()[0] in skip_words:
        return ""
    return name


def _extract_phone(text: str) -> str:
    """Extract phone number from text."""
    match = PHONE_RE.search(text)
    if match:
        return match.group(0).strip()
    return ""


def _extract_email(text: str) -> str:
    """Extract email from text."""
    match = EMAIL_RE.search(text)
    if match:
        return match.group(0).strip().lower()
    return ""


def _extract_owner_from_text(text: str) -> str:
    """Extract person name from text using patterns."""
    patterns = [
        r"(?:owner|founder|president|ceo|principal|director|manager)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
        r"(?:Owner|Founder|President|CEO|Principal|Director|Manager)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
        r"([A-Z][a-z]+ [A-Z][a-z]+),?\s+(?:Owner|Founder|President|CEO)",
        r"(?:founded by|started by|led by)\s+([A-Z][a-z]+ [A-Z][a-z]+)",
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            name = match.group(1).strip()
            if _is_valid_person_name(name):
                return name
    return ""


def _extract_owner_from_html(html: str) -> str:
    """Extract owner name from HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return _extract_owner_from_text(text)


def _is_valid_person_name(name: str) -> bool:
    """Validate person name."""
    if not name or len(name) < 4 or len(name) > 40:
        return False
    parts = name.split()
    if len(parts) < 2 or len(parts) > 4:
        return False
    if any(c.isdigit() for c in name):
        return False
    bad = {"the", "and", "for", "our", "all", "best", "top", "new", "air", "heat", "cool",
           "plumb", "roof", "electric", "service", "company", "group", "team", "inc", "llc"}
    if parts[0].lower() in bad:
        return False
    if not all(p[0].isupper() and p[1:].islower() for p in parts):
        return False
    return True


async def find_leads(
    niche: str,
    city: str,
    state: str,
    count: int = 100,
    progress_callback=None,
) -> List[Dict]:
    """
    Main lead finding function. Runs multiple sources in parallel.

    Args:
        niche: Business type (HVAC, Medical, etc.)
        city: City name
        state: State abbreviation
        count: Target number of leads
        progress_callback: async fn(phase, current, total) for progress updates

    Returns:
        List of verified lead dicts
    """
    logger.info(f"Finding {count} {niche} leads in {city}, {state}")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        phase = 1
        total_phases = 4

        if progress_callback:
            await progress_callback("searching_businesses", 0, 0)

        tasks = [
            _search_businesses(niche, city, state, client),
            _search_npi(niche, city, state, client),
            _search_bbb(niche, city, state, client),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_leads = []
        for r in results:
            if isinstance(r, list):
                all_leads.extend(r)

        logger.info(f"Phase 1: Found {len(all_leads)} raw leads")

        seen = set()
        unique_leads = []
        for lead in all_leads:
            key = lead["business_name"].lower().strip()
            if key not in seen and key:
                seen.add(key)
                unique_leads.append(lead)

        logger.info(f"Deduped: {len(unique_leads)} unique leads")

        if progress_callback:
            await progress_callback("finding_owners", 0, len(unique_leads))

        owner_tasks = []
        for lead in unique_leads:
            if not lead.get("owner_name"):
                owner_tasks.append(_find_owner_for_lead(lead, client))

        if owner_tasks:
            owner_results = await asyncio.gather(*owner_tasks, return_exceptions=True)
            idx = 0
            for lead in unique_leads:
                if not lead.get("owner_name"):
                    if idx < len(owner_results) and isinstance(owner_results[idx], str):
                        lead["owner_name"] = owner_results[idx]
                    idx += 1

        owners_found = sum(1 for l in unique_leads if l.get("owner_name"))
        logger.info(f"Phase 2: Owners found: {owners_found}/{len(unique_leads)}")

        if progress_callback:
            await progress_callback("verifying", len(unique_leads), len(unique_leads))

        verified = []
        for lead in unique_leads:
            if lead.get("business_name") and (lead.get("phone") or lead.get("website")):
                verified.append(lead)

        logger.info(f"Phase 3: {len(verified)} verified leads")

        if progress_callback:
            await progress_callback("complete", len(verified), len(verified))

        return verified[:count]
