"""Scrape search results for product candidate URLs (Bing + DuckDuckGo fallback + direct store + demo)."""
import re
from typing import List
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from src.fetch.http_client import fetch

BING_URL = "https://www.bing.com/search"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
MAX_RESULTS = 15

# Direct US store search URLs
STORE_SEARCH = [
    ("amazon.com", "https://www.amazon.com/s?k={q}"),
    ("bestbuy.com", "https://www.bestbuy.com/site/searchpage.jsp?st={q}"),
    ("walmart.com", "https://www.walmart.com/search?q={q}"),
    ("target.com", "https://www.target.com/s?searchTerm={q}"),
    ("ebay.com", "https://www.ebay.com/sch/i.html?_nkw={q}"),
]

# Demo: store search URLs shown when no products extracted (user can click to search)


def _build_query(intent_keywords: List[str], raw_query: str) -> str:
    if intent_keywords:
        parts = intent_keywords + ["buy", "USA"]
        return " ".join(parts[:8])
    return f"{raw_query} buy USA"


def _extract_links_bing(html: str, base: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    for sel in ["li.b_algo", "li[class*='b_algo']", "#b_results li"]:
        for li in soup.select(sel):
            a = li.find("a", href=True)
            if not a:
                continue
            href = a.get("href", "").strip()
            if _is_valid_link(href):
                full = urljoin(base, href)
                if _is_good_url(full):
                    links.append(full)
        if links:
            break
    if not links:
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if _is_valid_link(href):
                full = urljoin(base, href)
                if _is_good_url(full) and full not in links:
                    links.append(full)
    return links


def _extract_links_ddg(html: str, base: str) -> List[str]:
    import urllib.parse
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if "uddg=" in href:
            m = re.search(r"uddg=([^&]+)", href)
            if m:
                try:
                    full = urllib.parse.unquote(m.group(1))
                    if _is_good_url(full):
                        links.append(full)
                except Exception:
                    pass
        elif _is_valid_link(href) and "duckduckgo" not in href:
            full = urljoin(base, href)
            if _is_good_url(full):
                links.append(full)
    return links


def _is_valid_link(href: str) -> bool:
    if not href or href.startswith("#") or href.startswith("javascript:"):
        return False
    if "bing.com" in href or "duckduckgo.com" in href or "microsoft.com" in href:
        return False
    return True


BLOCKED_DOMAINS = (
    "bing.com", "microsoft.com", "live.com", "duckduckgo.com", "google.com",
    "yahoo.com", "facebook.com", "twitter.com", "youtube.com", "wikipedia.org",
    "linkedin.com", "instagram.com", "tiktok.com", "reddit.com", "pinterest.com",
)


def _is_good_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    u = url.lower()
    if any(b in u for b in BLOCKED_DOMAINS):
        return False
    bad = ("/login", "/signin", "/account", "/cart", "/checkout", "/help", "/contact")
    return not any(b in u for b in bad)


def _search_bing(query: str, max_results: int) -> List[str]:
    url = f"{BING_URL}?q={quote_plus(query)}&cc=US&setlang=en"
    text, _ = fetch(url)
    if not text or len(text) < 500:
        return []
    links = _extract_links_bing(text, BING_URL)
    return _dedupe(links, max_results)


def _search_ddg(query: str, max_results: int) -> List[str]:
    import requests
    try:
        r = requests.post(
            DDG_HTML_URL,
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"},
            timeout=15,
        )
        text = r.text if r.ok else ""
    except Exception:
        return []
    if not text or len(text) < 500:
        return []
    links = _extract_links_ddg(text, DDG_HTML_URL)
    return _dedupe(links, max_results)


def _fallback_store_urls(query: str, max_results: int) -> List[str]:
    """Direct product search pages as fallback when search engines fail."""
    q = quote_plus(" ".join(query.split()[:5]))  # first 5 words
    urls: List[str] = []
    for _, template in STORE_SEARCH:
        url = template.format(q=q)
        if url not in urls:
            urls.append(url)
        if len(urls) >= max_results:
            break
    return urls


def _dedupe(links: List[str], max_results: int) -> List[str]:
    seen = set()
    out: List[str] = []
    for u in links:
        u_norm = re.sub(r"[?#].*", "", u).rstrip("/")
        if u_norm not in seen and len(out) < max_results:
            seen.add(u_norm)
            out.append(u)
    return out


def _extract_product_links_from_store_page(html: str, base_url: str, limit: int = 12) -> List[str]:
    """Extract product page links from Amazon/BestBuy/Walmart search HTML."""
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    seen: set = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or len(href) < 10:
            continue
        full = urljoin(base_url, href)
        ok = False
        if "amazon.com" in full and ("/dp/" in href or "/gp/product/" in href):
            ok = True
        elif "bestbuy.com" in full and "site/" in href and (".p?" in href or ".p" in href):
            ok = True
        elif "walmart.com" in full and "/ip/" in href:
            ok = True
        elif "target.com" in full and "/p/" in href:
            ok = True
        elif "ebay.com" in full and "/itm/" in href:
            ok = True
        if ok and _is_good_url(full) and full not in seen:
            seen.add(full)
            links.append(full)
            if len(links) >= limit:
                break

    if not links and "amazon.com" in base_url:
        for tag in soup.find_all(attrs={"data-asin": True}):
            asin = tag.get("data-asin", "").strip()
            if asin and len(asin) == 10 and asin.isalnum():
                u = f"https://www.amazon.com/dp/{asin}"
                if u not in seen:
                    seen.add(u)
                    links.append(u)
                if len(links) >= limit:
                    break
    return links


def get_demo_results(user_input: str, intent_keywords: List[str] | None) -> List[dict]:
    """Return demo product cards when search/extract fails - store search links with reasons."""
    query = _build_query(intent_keywords or [], user_input)
    urls = _fallback_store_urls(query, 5)
    kw = " ".join((intent_keywords or [])[:5]) or user_input[:50]
    retailers = [("Amazon", "amazon.com"), ("Best Buy", "bestbuy.com"), ("Walmart", "walmart.com"), ("Target", "target.com"), ("eBay", "ebay.com")]
    results = []
    for i, url in enumerate(urls[:5]):
        name = next((r[0] for r in retailers if r[1] in url), "Store")
        results.append({
            "name": f"{name} - Search for '{kw}'",
            "price": "See site for current prices",
            "url": url,
            "image_url": "",
            "platform": name,
            "seller": "",
            "reasons": [
                f"Recommended for your search: '{kw}'.",
                f"US-based retailer {name} with competitive pricing.",
                "Click to view live product listings and availability.",
                "Wide selection of products matching your criteria.",
                "Secure checkout and reliable shipping options.",
            ],
            "evidence": [("source", name), ("query", kw), ("url", url)],
        })
    return results


def search_product_urls(
    user_input: str, intent_keywords: List[str] | None = None, max_results: int = MAX_RESULTS
) -> List[str]:
    """Return product URLs. Prioritize: store pages -> extract from store -> Bing -> DDG -> store search."""
    query = _build_query(intent_keywords or [], user_input)
    urls: List[str] = []

    store_urls = _fallback_store_urls(query, 3)
    for store_url in store_urls:
        text, _ = fetch(store_url)
        if text and len(text) > 2000:
            product_links = _extract_product_links_from_store_page(text, store_url, limit=8)
            if product_links:
                urls.extend(product_links)
                urls = _dedupe(urls, max_results)
                if urls:
                    return urls

    urls = _search_bing(query, max_results)
    urls = [u for u in urls if _is_good_url(u)]
    if not urls:
        urls = _search_ddg(query, max_results)
        urls = [u for u in urls if _is_good_url(u)]
    if not urls:
        urls = store_urls
    return _dedupe(urls, max_results)
