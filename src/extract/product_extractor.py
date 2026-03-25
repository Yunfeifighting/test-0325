"""Extract Product fields from HTML: JSON-LD first, then meta/fallback."""
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from bs4 import BeautifulSoup


@dataclass
class ProductInfo:
    name: str = ""
    price: Optional[float] = None
    currency: str = "USD"
    url: str = ""
    brand: str = ""
    description: str = ""
    price_source: str = ""
    raw_fields: dict = field(default_factory=dict)


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
        if isinstance(obj.get("brand"), dict):
            out["brand"] = obj.get("brand", {}).get("name", "")
        elif isinstance(obj.get("brand"), str):
            out["brand"] = obj.get("brand", "")
        offers = obj.get("offers")
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
    for meta in soup.find_all("meta", attrs={"name": True}):
        n = (meta.get("name") or "").lower()
        c = meta.get("content", "")
        if n in ("twitter:title", "product:title") and not out.get("name"):
            out["name"] = c
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

    if not info.name:
        title = soup.find("title")
        if title and title.string:
            info.name = title.string.strip()[:200]

    # IMPORTANT:
    # Do not use plain-text regex price as final price, because it often matches
    # unrelated amounts like gift-card promos, shipping thresholds, etc.
    # Keep only structured sources (JSON-LD/meta) for price accuracy.
    if info.price is None:
        body = soup.get_text()[:3000]
        p, c = _extract_price_from_text(body)
        if p is not None:
            info.raw_fields.setdefault("text_price_candidate", p)
            info.raw_fields.setdefault("text_price_currency_candidate", c)

    return info
