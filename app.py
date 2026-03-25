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
            image_url=cached.get("image_url", ""),
            platform=cached.get("platform", ""),
            seller=cached.get("seller", ""),
            price_source=cached.get("price_source", ""),
            raw_fields=cached.get("raw_fields", {}),
        )]
    infos = extract_products(html, url)
    if not infos:
        infos = [ProductInfo(url=url, name="Product")]
        set_(key, {"name": "Product", "url": url, "price": None, "currency": "USD",
                   "brand": "", "description": "", "image_url": "", "platform": "",
                   "seller": "", "price_source": "", "raw_fields": {}}, max_age_hours=24)
    elif infos:
        first = infos[0]
        set_(key, {"name": first.name, "price": first.price, "currency": first.currency,
                   "url": first.url, "brand": first.brand, "description": first.description,
                   "image_url": first.image_url, "platform": first.platform, "seller": first.seller,
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
            "image_url": p.image_url,
            "platform": p.platform,
            "seller": p.seller,
            "reasons": [r["text"] for r in reasons],
            "evidence": [(r["evidence"][0], r["evidence"][1]) for r in reasons],
        })
    return results


def _truncate(s: str, n: int) -> str:
    s = s or ""
    if len(s) <= n:
        return s
    return s[: max(0, n - 3)] + "..."


def _inject_tech_css() -> None:
    # Background + light UI accents. Keep it subtle for readability.
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"] {
            background: radial-gradient(1200px circle at 20% 10%, rgba(0, 255, 255, 0.12), rgba(0,0,0,0) 45%),
                        radial-gradient(900px circle at 80% 30%, rgba(0, 140, 255, 0.10), rgba(0,0,0,0) 50%),
                        linear-gradient(180deg, #04101f 0%, #030915 60%, #03070f 100%);
            color: #e6f3ff;
        }
        [data-testid="stAppViewContainer"]::before{
            content:'';
            position:fixed;
            inset:0;
            background:
                repeating-linear-gradient(90deg, rgba(0,200,255,0.08) 0px, rgba(0,200,255,0.08) 1px, transparent 1px, transparent 70px),
                repeating-linear-gradient(0deg, rgba(0,200,255,0.06) 0px, rgba(0,200,255,0.06) 1px, transparent 1px, transparent 70px);
            opacity:0.18;
            pointer-events:none;
            z-index:0;
        }
        [data-testid="stAppViewContainer"] > *{
            position:relative;
            z-index:1;
        }
        .badgebar{display:flex; gap:8px; flex-wrap:wrap; margin:6px 0 8px;}
        .badge{
            background: rgba(0,160,255,0.12);
            border: 1px solid rgba(0,200,255,0.35);
            color:#cfefff;
            padding:4px 10px;
            border-radius:999px;
            font-size:0.85rem;
            line-height:1.2;
        }
        .stButton>button{
            border: 1px solid rgba(0,200,255,0.35);
            background: rgba(0, 120, 255, 0.10);
            color:#dff7ff;
        }
        .stButton>button:hover{
            border-color: rgba(0,220,255,0.80);
            background: rgba(0, 120, 255, 0.20);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(page_title="US Product Search & Recommendations", layout="wide")
    _inject_tech_css()
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

        # 2-column grid cards
        for i in range(0, len(results), 2):
            row_cols = st.columns(2)
            for col_i in range(2):
                idx = i + col_i
                if idx >= len(results):
                    continue
                r = results[idx]

                with row_cols[col_i]:
                    with st.container(border=True):
                        name = r.get("name") or "Unknown product"
                        st.subheader(f"{idx + 1}. {_truncate(name, 72)}")

                        image_url = r.get("image_url") or ""
                        if image_url:
                            st.image(image_url, use_container_width=True)

                        platform_text = (r.get("platform") or "").strip() or "Unknown platform"
                        seller_text = (r.get("seller") or "").strip() or ""
                        seller_badge = f"<span class='badge'>Seller: {seller_text}</span>" if seller_text else ""

                        st.markdown(
                            f"""
                            <div class="badgebar">
                              <span class='badge'>Platform: {platform_text}</span>
                              {seller_badge}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        if r.get("price"):
                            st.write(f"**Price:** {r['price']}")

                        url = r.get("url") or ""
                        if url:
                            st.markdown(f"**Link:** [{_truncate(url, 52)}]({url})")

                        with st.expander("Details (reasons & evidence)", expanded=False):
                            st.markdown("**Recommendation reasons:**")
                            for reason in r.get("reasons", []):
                                st.write(f"- {reason}")

                            with st.expander("Evidence (traceable fields)", expanded=False):
                                for field, value in r.get("evidence", []):
                                    st.code(f"{field}: {str(value)[:120]}", language=None)


if __name__ == "__main__":
    main()
