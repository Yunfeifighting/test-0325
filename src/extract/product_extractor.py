"""Extract Product fields from HTML: JSON-LD first, then meta/fallback."""
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass
class ProductInfo:
    name: str = ""
    price: Optional[float] = None
    currency: str = "USD"
    url: str = ""
    brand: str = ""
    description: str = ""
    image_url: str = ""
    platform: str = ""
    seller: str = ""
    price_source: str = ""
    raw_fields: dict = field(default_factory=dict)


def _platform_from_url(url: str) -> str:
    if not url:
        return ""
    m = re.search(r"https?://(?:www\.)?([^/]+)", url, re.I)
    if not m:
        return ""
    host = (m.group(1) or "").lower()
    root = ".".join(host.split(".")[-2:]) if "." in host else host
    names = {
        "amazon.com": "Amazon",
        "walmart.com": "Walmart",
        "target.com": "Target",
        "bestbuy.com": "Best Buy",
        "ebay.com": "eBay",
        "costco.com": "Costco",
        "newegg.com": "Newegg",
        "homedepot.com": "The Home Depot",
        "lowes.com": "Lowe's",
    }
    return names.get(root, root)


def _normalize_image_url(v: Any) -> str:
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, list):
        for x in v:
            if isinstance(x, str) and x.strip():
                return x.strip()
            if isinstance(x, dict):
                candidate = x.get("url") or x.get("contentUrl")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
    if isinstance(v, dict):
        candidate = v.get("url") or v.get("contentUrl")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _extract_seller_from_offers(offers: Any) -> str:
    if isinstance(offers, dict):
        seller = offers.get("seller")
        if isinstance(seller, dict):
            return str(seller.get("name") or "")
        if isinstance(seller, str):
            return seller
    if isinstance(offers, list):
        for o in offers:
            if not isinstance(o, dict):
                continue
            seller = o.get("seller")
            if isinstance(seller, dict) and seller.get("name"):
                return str(seller.get("name"))
            if isinstance(seller, str) and seller:
                return seller
    return ""


def _resolve_img_url(src: str, page_url: str) -> str:
    """Resolve potentially relative image URL to absolute."""
    if not src or not src.strip():
        return ""
    src = src.strip()
    if src.startswith("data:"):
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return urljoin(page_url, src)
    if not src.startswith("http"):
        return urljoin(page_url, src)
    return src


def _is_product_image(src: str) -> bool:
    """Filter out icons, tracking pixels, tiny placeholders."""
    if not src:
        return False
    low = src.lower()
    skip = (
        "pixel", "beacon", "track", "spacer", "blank", "logo", "icon",
        "sprite", "1x1", "spinner", "loading", "placeholder",
        "data:image", ".gif", "transparent", "arrow", "chevron",
        "badge", "rating", "star", "banner",
    )
    return not any(s in low for s in skip)


def _extract_image_from_html(soup: BeautifulSoup, page_url: str) -> str:
    """Deep HTML fallback: site-specific selectors, then generic heuristics."""
    host = (page_url or "").lower()

    selectors: list[str] = []

    if "amazon." in host:
        selectors = [
            "#imgTagWrapperId img",
            "#landingImage",
            "#main-image-container img",
            "#imageBlock img",
            "#ebooksImgBlkFront",
            "img#imgBlkFront",
            "[data-a-image-name='landingImage']",
        ]
    elif "walmart." in host:
        selectors = [
            "[data-testid='hero-image-container'] img",
            ".prod-hero-image img",
            "[data-testid='media-thumbnail'] img",
            ".hover-zoom-hero-image img",
        ]
    elif "bestbuy." in host:
        selectors = [
            ".primary-image img",
            ".shop-media-gallery img",
            "[data-testid='image-media-container'] img",
            ".picture-wrapper img",
        ]
    elif "target." in host:
        selectors = [
            "[data-test='product-image'] img",
            "[data-test='product-detail'] img",
            ".slideDeckPicture img",
        ]
    elif "ebay." in host:
        selectors = [
            "#icImg",
            ".ux-image-carousel img",
            "[data-testid='ux-image-carousel'] img",
            ".img-transition-medium",
        ]
    elif "newegg." in host:
        selectors = [
            ".product-view-img-original",
            ".swiper-slide img",
            ".product-main-aside img",
        ]

    selectors += [
        "[itemprop='image']",
        "main img[src*='product']",
        "main img[src*='item']",
        "#product-image img",
        ".product-image img",
        ".product-img img",
        ".pdp-image img",
        ".gallery img",
        "[data-component='image'] img",
    ]

    for sel in selectors:
        try:
            el = soup.select_one(sel)
        except Exception:
            continue
        if not el:
            continue
        tag = el if el.name == "img" else el.find("img")
        if not tag:
            tag = el
        src = (
            tag.get("src")
            or tag.get("data-src")
            or tag.get("data-old-hires")
            or tag.get("data-a-dynamic-image", "")
        )
        if isinstance(src, str) and "{" in src:
            try:
                img_dict = json.loads(src)
                if isinstance(img_dict, dict) and img_dict:
                    src = max(img_dict.keys(), key=lambda k: sum(img_dict.get(k, [0, 0])))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        resolved = _resolve_img_url(str(src or ""), page_url)
        if resolved and _is_product_image(resolved):
            return resolved

    candidates: list[tuple[int, str]] = []
    for img in soup.find_all("img", src=True):
        src = str(img.get("src") or img.get("data-src") or "")
        resolved = _resolve_img_url(src, page_url)
        if not resolved or not _is_product_image(resolved):
            continue
        w = 0
        try:
            w = int(img.get("width") or 0)
        except (ValueError, TypeError):
            pass
        h = 0
        try:
            h = int(img.get("height") or 0)
        except (ValueError, TypeError):
            pass
        area = max(w, 1) * max(h, 1)
        if w and w < 50:
            continue
        if h and h < 50:
            continue
        candidates.append((area, resolved))

    if candidates:
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    return ""


def _parse_json_ld(script_text: str) -> list[dict]:
    try:
        data = json.loads(script_text)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def _extract_from_product_schema(obj: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj.get("@type"), str) and "Product" in obj.get("@type", ""):
        out["name"] = obj.get("name") or obj.get("title") or ""
        out["description"] = obj.get("description") or ""
        out["image_url"] = _normalize_image_url(obj.get("image"))
        if isinstance(obj.get("brand"), dict):
            out["brand"] = obj.get("brand", {}).get("name", "")
        elif isinstance(obj.get("brand"), str):
            out["brand"] = obj.get("brand", "")
        offers = obj.get("offers")
        seller = _extract_seller_from_offers(offers)
        if seller:
            out["seller"] = seller
        if isinstance(offers, dict):
            price = offers.get("price")
            curr = offers.get("priceCurrency", "USD")
            if price is not None:
                try:
                    out["price"] = float(price)
                    out["currency"] = str(curr).upper() if curr else "USD"
                    out["price_source"] = "jsonld.offers.price"
                except (ValueError, TypeError):
                    pass
        elif isinstance(offers, list) and offers:
            for o in offers:
                if not isinstance(o, dict):
                    continue
                price = o.get("price")
                curr = o.get("priceCurrency", "USD")
                if price is not None:
                    try:
                        out["price"] = float(price)
                        out["currency"] = str(curr).upper() if curr else "USD"
                        out["price_source"] = "jsonld.offers[].price"
                        break
                    except (ValueError, TypeError):
                        continue
        out["raw"] = {k: v for k, v in obj.items() if not k.startswith("@")}
    return out


def _extract_from_aggregate_offer(obj: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    t = obj.get("@type")
    if isinstance(t, str) and "AggregateOffer" in t:
        low = obj.get("lowPrice")
        high = obj.get("highPrice")
        price = obj.get("price")
        curr = obj.get("priceCurrency", "USD")
        try:
            if low is not None:
                out["price"] = float(low)
            elif price is not None:
                out["price"] = float(price)
            elif high is not None:
                out["price"] = float(high)
            if out.get("price") is not None:
                out["currency"] = str(curr).upper() if curr else "USD"
                out["price_source"] = "jsonld.aggregate_offer"
        except (ValueError, TypeError):
            pass
    return out


def _extract_meta(soup: BeautifulSoup) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for meta in soup.find_all("meta", property=True):
        p = meta.get("property", "").lower()
        c = meta.get("content", "")
        if "og:title" in p:
            out.setdefault("name", c)
        elif "product:price:amount" in p or "og:price:amount" in p:
            try:
                out["price"] = float(c)
                out["price_source"] = f"meta:{p}"
            except (ValueError, TypeError):
                pass
        elif "product:price:currency" in p or "og:price:currency" in p:
            out["currency"] = (c or "USD").upper()
        elif "og:image" in p and c:
            out.setdefault("image_url", c)
    for meta in soup.find_all("meta", attrs={"name": True}):
        n = (meta.get("name") or "").lower()
        c = meta.get("content", "")
        if n in ("twitter:title", "product:title") and not out.get("name"):
            out["name"] = c
        elif n in ("twitter:image", "image") and c and not out.get("image_url"):
            out["image_url"] = c
    return out


def _extract_price_from_text(text: str) -> tuple[Optional[float], str]:
    # Look for $XX.XX or USD XX.XX
    m = re.search(r'\$[\d,]+\.?\d*|USD\s*[\d,]+\.?\d*', text, re.I)
    if m:
        s = re.sub(r'[^\d.]', '', m.group().replace(',', ''))
        try:
            return float(s), "USD"
        except ValueError:
            pass
    return None, "USD"


def _extract_from_item_list(obj: dict, page_url: str) -> list[ProductInfo]:
    """Extract multiple products from ItemList schema (search/category pages)."""
    out: list[ProductInfo] = []
    items = obj.get("itemListElement") or obj.get("itemList") or []
    if not isinstance(items, list):
        return out
    for i, item in enumerate(items[:10]):
        if not isinstance(item, dict):
            continue
        sub = item.get("item") if isinstance(item.get("item"), dict) else item
        t = sub.get("@type") if isinstance(sub, dict) else ""
        if isinstance(t, str) and "Product" in t:
            d = _extract_from_product_schema(sub)
            info = ProductInfo(url=page_url)
            info.name = d.get("name", "")
            info.price = d.get("price")
            info.currency = d.get("currency", "USD")
            info.brand = d.get("brand", "")
            info.description = d.get("description", "")
            raw_img = d.get("image_url", "")
            info.image_url = _resolve_img_url(raw_img, page_url) if raw_img else ""
            info.seller = d.get("seller", "")
            info.platform = _platform_from_url(page_url)
            info.raw_fields = d.get("raw", {})
            if info.name or info.price is not None:
                out.append(info)
    return out


def extract_products(html: str, url: str = "") -> list[ProductInfo]:
    """Extract one or more products (e.g. from ItemList on search pages)."""
    soup = BeautifulSoup(html, "lxml")
    all_products: list[ProductInfo] = []

    for script in soup.find_all("script", type="application/ld+json"):
        txt = script.string or ""
        for obj in _parse_json_ld(txt):
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type")
            if isinstance(t, str) and "ItemList" in t:
                all_products.extend(_extract_from_item_list(obj, url))
    if all_products:
        return all_products
    return [extract_product(html, url)]


def extract_product(html: str, url: str = "") -> ProductInfo:
    """Extract product info from HTML. JSON-LD Product first, then meta, then text fallback."""
    info = ProductInfo(url=url)
    info.platform = _platform_from_url(url)
    soup = BeautifulSoup(html, "lxml")

    for script in soup.find_all("script", type="application/ld+json"):
        txt = script.string or ""
        for obj in _parse_json_ld(txt):
            if not isinstance(obj, dict):
                continue
            t = obj.get("@type")
            if isinstance(t, str):
                if "Product" in t:
                    d = _extract_from_product_schema(obj)
                    if d.get("name"):
                        info.name = info.name or str(d.get("name", ""))
                    if d.get("price") is not None:
                        info.price = d["price"]
                        info.currency = d.get("currency", "USD")
                        info.price_source = d.get("price_source", info.price_source)
                    if d.get("brand"):
                        info.brand = info.brand or str(d.get("brand", ""))
                    if d.get("description"):
                        info.description = info.description or str(d.get("description", ""))
                    if d.get("image_url"):
                        info.image_url = info.image_url or str(d.get("image_url", ""))
                    if d.get("seller"):
                        info.seller = info.seller or str(d.get("seller", ""))
                    info.raw_fields.update(d.get("raw", {}))
                elif "AggregateOffer" in t:
                    d = _extract_from_aggregate_offer(obj)
                    if d.get("price") is not None and info.price is None:
                        info.price = d["price"]
                        info.currency = d.get("currency", "USD")
                        info.price_source = d.get("price_source", info.price_source)

    meta = _extract_meta(soup)
    if meta.get("name") and not info.name:
        info.name = meta["name"]
    if meta.get("price") is not None and info.price is None:
        info.price = meta["price"]
        info.currency = meta.get("currency", "USD")
        info.price_source = meta.get("price_source", info.price_source)
    if meta.get("image_url") and not info.image_url:
        info.image_url = str(meta.get("image_url", ""))

    if not info.name:
        title = soup.find("title")
        if title and title.string:
            info.name = title.string.strip()[:200]
    if not info.seller:
        seller_meta = soup.find("meta", attrs={"name": re.compile(r"(seller|merchant|store)", re.I)})
        if seller_meta and seller_meta.get("content"):
            info.seller = seller_meta.get("content", "").strip()

    if info.image_url:
        info.image_url = _resolve_img_url(info.image_url, url)
    if not info.image_url or not _is_product_image(info.image_url):
        info.image_url = _extract_image_from_html(soup, url)

    if info.price is None:
        body = soup.get_text()[:3000]
        p, c = _extract_price_from_text(body)
        if p is not None:
            info.raw_fields.setdefault("text_price_candidate", p)
            info.raw_fields.setdefault("text_price_currency_candidate", c)

    return info
