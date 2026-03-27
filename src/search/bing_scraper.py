"""Scrape search results for product candidate URLs (Bing + DuckDuckGo + store fallback)."""
import re
from typing import List, Dict
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from src.fetch.http_client import fetch

BING_URL = "https://www.bing.com/search"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
MAX_RESULTS = 15

STORE_SEARCH = [
    ("amazon.com", "https://www.amazon.com/s?k={q}"),
    ("bestbuy.com", "https://www.bestbuy.com/site/searchpage.jsp?st={q}"),
    ("walmart.com", "https://www.walmart.com/search?q={q}"),
    ("target.com", "https://www.target.com/s?searchTerm={q}"),
    ("ebay.com", "https://www.ebay.com/sch/i.html?_nkw={q}"),
]

_bing_thumbnails: Dict[str, str] = {}
_bing_titles: Dict[str, str] = {}
_bing_snippet_prices: Dict[str, float] = {}


def _reset_bing_artifacts() -> None:
    global _bing_thumbnails, _bing_titles, _bing_snippet_prices
    _bing_thumbnails = {}
    _bing_titles = {}
    _bing_snippet_prices = {}


def _normalize_img_url(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("//"):
        return "https:" + u
    return u


def _img_url_from_tag(img) -> str:
    if not img:
        return ""
    for attr in ("src", "data-src-hq", "data-src", "data-lazy-src", "data-original"):
        v = _normalize_img_url(str(img.get(attr) or ""))
        if v.startswith("http"):
            return v
    srcset = (img.get("srcset") or "").strip()
    if srcset:
        parts = [p.strip().split()[0] for p in srcset.split(",") if p.strip()]
        if parts:
            return _normalize_img_url(parts[-1])
    return ""


def _extract_price_from_snippet(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"\$[\d,]+\.?\d*", text)
    if not m:
        return None
    s = re.sub(r"[^\d.]", "", m.group().replace(",", ""))
    try:
        p = float(s)
        if 0.5 <= p <= 50000.0:
            return p
    except ValueError:
        pass
    return None


def _build_query(intent_keywords: List[str], raw_query: str) -> str:
    if intent_keywords:
        parts = intent_keywords + ["buy", "USA"]
        return " ".join(parts[:8])
    return f"{raw_query} buy USA"


def _extract_links_bing(html: str, base: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []

    for li in soup.select("li.b_algo, li[class*='b_algo']"):
        a = li.find("a", href=True)
        if not a:
            continue
        href = a.get("href", "").strip()
        if not _is_valid_link(href):
            continue
        full = urljoin(base, href)
        if not _is_good_url(full):
            continue
        links.append(full)

        title = a.get_text(separator=" ", strip=True)
        if title and len(title) > 3:
            _bing_titles[full] = title[:240]

        cap = li.select_one(".b_caption, .b_snippet, p")
        snippet = cap.get_text(" ", strip=True) if cap else ""
        sp = _extract_price_from_snippet(snippet)
        if sp is not None:
            _bing_snippet_prices[full] = sp

        for img in li.find_all("img"):
            thumb = _img_url_from_tag(img)
            if thumb.startswith("http"):
                low = thumb.lower()
                if "favicon" in low or "sprite" in low:
                    continue
                _bing_thumbnails[full] = thumb
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


def _is_product_page_url(url: str) -> bool:
    """Heuristic: does URL look like an individual product page?"""
    u = url.lower()
    patterns = (
        "/dp/", "/gp/product/", "/ip/", "/itm/", "/p/", "/product/",
        "/products/", "sku=", "item=", "productid=", ".p?", "/pd/",
    )
    return any(p in u for p in patterns)


def _is_blocked_or_captcha(html: str) -> bool:
    if not html or len(html) < 800:
        return True
    low = html[:2000].lower()
    captcha_markers = ("captcha", "robot", "automated access", "are you a human", "verify you are")
    return any(m in low for m in captcha_markers)


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
    q = quote_plus(" ".join(query.split()[:5]))
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
    if _is_blocked_or_captcha(html):
        return []

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

    if not links and "amazon.com" in base_url:
        for m in re.finditer(r'/dp/([A-Z0-9]{10})', html):
            u = f"https://www.amazon.com/dp/{m.group(1)}"
            if u not in seen:
                seen.add(u)
                links.append(u)
            if len(links) >= limit:
                break

    return links


def _url_match_keys(url: str) -> List[str]:
    u = (url or "").strip()
    if not u:
        return []
    no_hash = u.split("#")[0]
    stripped = no_hash.rstrip("/")
    keys = [u, no_hash, stripped]
    if stripped:
        keys.append(stripped + "/")
    out: List[str] = []
    for k in keys:
        if k and k not in out:
            out.append(k)
    return out


def get_bing_thumbnail(url: str) -> str:
    for k in _url_match_keys(url):
        v = _bing_thumbnails.get(k)
        if v:
            return v
    return ""


def get_bing_title(url: str) -> str:
    for k in _url_match_keys(url):
        v = _bing_titles.get(k)
        if v:
            return v
    return ""


def get_bing_snippet_price(url: str) -> float | None:
    for k in _url_match_keys(url):
        v = _bing_snippet_prices.get(k)
        if v is not None:
            return v
    return None


def get_demo_results(user_input: str, intent_keywords: List[str] | None) -> List[dict]:
    query = _build_query(intent_keywords or [], user_input)
    urls = _fallback_store_urls(query, 5)
    kw = " ".join((intent_keywords or [])[:5]) or user_input[:50]
    retailers = [("Amazon", "amazon.com"), ("Best Buy", "bestbuy.com"),
                 ("Walmart", "walmart.com"), ("Target", "target.com"), ("eBay", "ebay.com")]
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
            ],
            "evidence": [("source", name), ("query", kw), ("url", url)],
        })
    return results


def search_product_urls(
    user_input: str, intent_keywords: List[str] | None = None, max_results: int = MAX_RESULTS
) -> List[str]:
    """Return product URLs. Bing first (gets direct product pages), then store extraction fallback."""
    query = _build_query(intent_keywords or [], user_input)
    _reset_bing_artifacts()
    urls: List[str] = []

    bing_urls = _search_bing(query, max_results)
    bing_urls = [u for u in bing_urls if _is_good_url(u)]

    product_urls = [u for u in bing_urls if _is_product_page_url(u)]
    other_urls = [u for u in bing_urls if not _is_product_page_url(u)]
    urls = product_urls + other_urls

    if len(urls) < 4:
        ddg_urls = _search_ddg(query, max_results)
        ddg_urls = [u for u in ddg_urls if _is_good_url(u)]
        urls.extend(ddg_urls)
        urls = _dedupe(urls, max_results)

    if len(urls) < 4:
        store_urls = _fallback_store_urls(query, 3)
        for store_url in store_urls:
            text, _ = fetch(store_url)
            if text and not _is_blocked_or_captcha(text):
                product_links = _extract_product_links_from_store_page(text, store_url, limit=6)
                if product_links:
                    urls.extend(product_links)

    if not urls:
        urls = _fallback_store_urls(query, 5)

    return _dedupe(urls, max_results)
