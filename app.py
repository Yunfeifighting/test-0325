"""Streamlit entry: natural language product search with traceable recommendations."""
import streamlit as st

from src.cache.cache import get_cached, set_
from src.extract.product_extractor import ProductInfo, extract_product, extract_products
from src.fetch.http_client import fetch
from src.match.intent import extract_intent
from src.match.ranker import rank_products
from src.reason.reason_builder import build_reasons
from src.search.bing_scraper import search_product_urls, get_demo_results

MAX_CANDIDATES = 12
MAX_FINAL = 8


def _cached_fetch(url: str) -> str | None:
    key = f"fetch:{url}"
    cached = get_cached(key)
    if cached is not None and isinstance(cached.get("html"), str):
        return cached["html"]
    text, _ = fetch(url)
    if text:
        set_(key, {"html": text[:500000]}, max_age_hours=24)
    return text


def _cached_extract(html: str, url: str) -> list[ProductInfo]:
    key = f"extract:{url}"
    cached = get_cached(key)
    if cached is not None and isinstance(cached, dict) and (cached.get("name") or cached.get("url")):
        return [ProductInfo(
            name=cached.get("name", ""),
            price=cached.get("price"),
            currency=cached.get("currency", "USD"),
            url=cached.get("url", url),
            brand=cached.get("brand", ""),
            description=cached.get("description", ""),
            price_source=cached.get("price_source", ""),
            raw_fields=cached.get("raw_fields", {}),
        )]
    infos = extract_products(html, url)
    if not infos:
        infos = [ProductInfo(url=url, name="Product")]
        set_(key, {"name": "Product", "url": url, "price": None, "currency": "USD",
                   "brand": "", "description": "", "price_source": "", "raw_fields": {}}, max_age_hours=24)
    elif infos:
        first = infos[0]
        set_(key, {"name": first.name, "price": first.price, "currency": first.currency,
                   "url": first.url, "brand": first.brand, "description": first.description,
                   "price_source": first.price_source,
                   "raw_fields": first.raw_fields}, max_age_hours=24)
    return infos


def run_pipeline(user_input: str) -> list[dict]:
    intent = extract_intent(user_input)
    urls = search_product_urls(
        user_input,
        intent_keywords=intent.keywords,
        max_results=MAX_CANDIDATES,
    )
    _blocked = ("bing.com", "microsoft.com", "duckduckgo.com", "google.com", "yahoo.com")
    _bad_names = ("guided by", "bing", "google", "search", "weather", "sign in", "login")

    products: list[ProductInfo] = []
    for url in urls:
        if any(b in url.lower() for b in _blocked):
            continue
        html = _cached_fetch(url)
        if not html:
            continue
        for info in _cached_extract(html, url):
            info.url = info.url or url
            if any(b in url.lower() for b in _blocked):
                continue
            if not info.name:
                info.name = info.url.split("/")[-1][:80] or "Product"
            if info.name and any(b in info.name.lower() for b in _bad_names):
                continue
            products.append(info)

    seen_urls = set()
    unique_products = []
    for p in products:
        u = (p.url or "").split("?")[0].rstrip("/")
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique_products.append(p)
    products = unique_products

    ranked = rank_products(
        products,
        user_input,
        intent.keywords,
        intent.budget_min,
        intent.budget_max,
    )[:MAX_FINAL]

    results = []
    for p in ranked:
        reasons = build_reasons(p, intent.keywords, intent.budget_min, intent.budget_max)
        price_display = f"${p.price:.2f}" if p.price is not None and p.currency == "USD" else None
        if p.price is not None and p.currency != "USD":
            price_display = f"{p.currency} {p.price:.2f} (non-USD)"
        if p.price is None:
            price_display = "Price unavailable (no reliable structured price found)"
        results.append({
            "name": p.name or "Unknown product",
            "price": price_display,
            "url": p.url,
            "reasons": [r["text"] for r in reasons],
            "evidence": [(r["evidence"][0], r["evidence"][1]) for r in reasons],
        })
    return results


def main():
    st.set_page_config(page_title="US Product Search & Recommendations", layout="wide")
    st.title("US Product Search & Recommendations")
    st.caption("Enter your needs in natural language. Results are limited to US-oriented sources and USD pricing when available.")

    user_input = st.text_area(
        "Describe what you are looking for (e.g., budget, use case, preferences):",
        height=100,
        placeholder="e.g., Wireless headphones under $100 for running, noise cancellation preferred",
    )

    if st.button("Search"):
        if not (user_input or "").strip():
            st.warning("Please enter a description of what you want.")
            return
        with st.spinner("Searching and analyzing products..."):
            results = run_pipeline(user_input.strip())
        if not results:
            intent = extract_intent(user_input.strip())
            results = get_demo_results(user_input.strip(), intent.keywords)
            if results:
                st.info("Direct search returned no results. Showing recommended retailers to search—click to view products.")
        if not results:
            st.warning("No results available. Check your network connection and try again.")
            return
        for i, r in enumerate(results, 1):
            with st.expander(f"**{i}. {r['name'][:80]}{'...' if len(r['name']) > 80 else ''}**", expanded=(i <= 3)):
                if r["price"]:
                    st.write(f"**Price:** {r['price']}")
                st.write(f"**Link:** [{r['url'][:60]}...]({r['url']})")
                st.write("**Recommendation reasons:**")
                for j, reason in enumerate(r["reasons"], 1):
                    st.write(f"- {reason}")
                with st.expander("Evidence (traceable fields)"):
                    for field, value in r["evidence"]:
                        st.code(f"{field}: {str(value)[:120]}", language=None)


if __name__ == "__main__":
    main()
