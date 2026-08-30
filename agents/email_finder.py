"""
email_finder.py — Extract emails from websites
"""

import asyncio
import logging
import re

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
GENERIC_PREFIXES = {"info", "contact", "admin", "support", "sales", "hello", "help", "office", "mail", "webmaster"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
}


async def find_emails_from_website(website: str, client: httpx.AsyncClient) -> list[str]:
    """Extract real person emails from a website."""
    if not website:
        return []

    emails = set()
    urls_to_check = [
        website.rstrip("/"),
        website.rstrip("/") + "/contact",
        website.rstrip("/") + "/about",
        website.rstrip("/") + "/about-us",
        website.rstrip("/") + "/team",
    ]

    for url in urls_to_check[:3]:
        try:
            resp = await client.get(url, headers=HEADERS, timeout=8, follow_redirects=True)
            if resp.status_code != 200:
                continue

            text = resp.text
            soup = BeautifulSoup(text, "html.parser")

            for mailto in soup.select("a[href^='mailto:']"):
                email = mailto["href"].replace("mailto:", "").split("?")[0].strip().lower()
                if _is_valid_email(email):
                    emails.add(email)

            page_emails = EMAIL_RE.findall(text)
            for e in page_emails:
                e = e.strip().lower().rstrip(".")
                if _is_valid_email(e):
                    emails.add(e)

            if emails:
                break

        except Exception:
            continue

    return sorted(emails)


def _is_valid_email(email: str) -> bool:
    """Check if email is valid and not generic."""
    if not email or len(email) < 6 or len(email) > 80:
        return False
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return False
    if any(email.startswith(p + "@") for p in GENERIC_PREFIXES):
        return False
    junk = {"example.com", "test.com", "sentry.io", "wixpress.com", "w3.org",
            "schema.org", "googleapis.com", "gstatic.com", "facebook.com"}
    domain = email.split("@")[1]
    if domain in junk:
        return False
    return True


async def enrich_leads_with_emails(leads: list[dict], max_concurrent: int = 8) -> list[dict]:
    """Add emails to leads that have websites."""
    sem = asyncio.Semaphore(max_concurrent)

    async def _process(lead):
        if lead.get("email") or not lead.get("website"):
            return lead
        async with sem:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    emails = await find_emails_from_website(lead["website"], client)
                    if emails:
                        lead["email"] = emails[0]
            except Exception:
                pass
        return lead

    tasks = [_process(lead) for lead in leads]
    await asyncio.gather(*tasks)
    return leads
