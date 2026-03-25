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


_PLATFORM_COLORS = {
    "Amazon": ("#ff9900", "#232f3e"),
    "Walmart": ("#0071dc", "#004c91"),
    "Target": ("#cc0000", "#990000"),
    "Best Buy": ("#0046be", "#001e73"),
    "eBay": ("#e53238", "#86b817"),
    "Costco": ("#e31837", "#005daa"),
    "Newegg": ("#f36c21", "#333"),
    "The Home Depot": ("#f96302", "#333"),
    "Lowe's": ("#004990", "#002f5f"),
}


def _inject_tech_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

        @keyframes bg-shift{
            0%{background-position:0% 50%}
            50%{background-position:100% 50%}
            100%{background-position:0% 50%}
        }
        @keyframes scanline{
            0%{top:-100%}
            100%{top:200%}
        }
        @keyframes pulse-glow{
            0%,100%{box-shadow:0 0 8px rgba(0,200,255,0.25), inset 0 0 8px rgba(0,200,255,0.05)}
            50%{box-shadow:0 0 20px rgba(0,200,255,0.45), inset 0 0 14px rgba(0,200,255,0.08)}
        }
        @keyframes neon-flicker{
            0%,19%,21%,23%,25%,54%,56%,100%{text-shadow:0 0 7px rgba(0,220,255,0.7), 0 0 20px rgba(0,180,255,0.4)}
            20%,24%,55%{text-shadow:none}
        }

        /* ── Base ── */
        html, body, [data-testid="stAppViewContainer"]{
            background: linear-gradient(135deg, #020b18 0%, #041428 25%, #030d1f 50%, #061830 75%, #020b18 100%);
            background-size: 400% 400%;
            animation: bg-shift 20s ease infinite;
            color: #d0eaff;
            font-family: 'Inter', sans-serif;
        }
        [data-testid="stHeader"]{background:transparent !important}
        [data-testid="stSidebar"]{background:rgba(3,12,28,0.92) !important; backdrop-filter:blur(12px)}

        /* ── Grid overlay ── */
        [data-testid="stAppViewContainer"]::before{
            content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
            background:
                repeating-linear-gradient(90deg, rgba(0,180,255,0.04) 0px, rgba(0,180,255,0.04) 1px, transparent 1px, transparent 80px),
                repeating-linear-gradient(0deg, rgba(0,180,255,0.03) 0px, rgba(0,180,255,0.03) 1px, transparent 1px, transparent 80px);
        }
        /* ── Scanline ── */
        [data-testid="stAppViewContainer"]::after{
            content:'';position:fixed;left:0;width:100%;height:120px;pointer-events:none;z-index:0;
            background:linear-gradient(180deg, transparent, rgba(0,200,255,0.04) 40%, rgba(0,200,255,0.07) 50%, rgba(0,200,255,0.04) 60%, transparent);
            animation:scanline 8s linear infinite;
        }
        [data-testid="stAppViewContainer"] > *{position:relative;z-index:1}

        /* ── Title ── */
        [data-testid="stAppViewContainer"] h1{
            font-family:'Inter',sans-serif !important;
            font-weight:700 !important;
            background: linear-gradient(90deg, #00d4ff 0%, #0090ff 40%, #00d4ff 80%, #80eaff 100%);
            background-size:200% auto;
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            animation:bg-shift 6s linear infinite;
            letter-spacing:-0.5px;
        }

        /* ── Search input ── */
        textarea, [data-testid="stTextArea"] textarea{
            background:rgba(0,20,50,0.65) !important;
            border:1px solid rgba(0,180,255,0.25) !important;
            border-radius:12px !important;
            color:#d8f0ff !important;
            font-family:'Inter',sans-serif !important;
            backdrop-filter:blur(6px);
            transition:border-color .3s, box-shadow .3s;
        }
        textarea:focus, [data-testid="stTextArea"] textarea:focus{
            border-color:rgba(0,200,255,0.65) !important;
            box-shadow:0 0 16px rgba(0,200,255,0.15) !important;
        }

        /* ── Search button ── */
        .stButton>button{
            background:linear-gradient(135deg, rgba(0,100,220,0.25), rgba(0,180,255,0.15)) !important;
            border:1px solid rgba(0,200,255,0.4) !important;
            border-radius:12px !important;
            color:#c8f0ff !important;
            font-weight:600 !important;
            font-family:'Inter',sans-serif !important;
            padding:0.6rem 2.4rem !important;
            letter-spacing:0.5px;
            transition:all .3s ease;
            animation:pulse-glow 3s ease-in-out infinite;
        }
        .stButton>button:hover{
            background:linear-gradient(135deg, rgba(0,120,240,0.4), rgba(0,200,255,0.3)) !important;
            border-color:rgba(0,230,255,0.8) !important;
            box-shadow:0 0 28px rgba(0,200,255,0.35) !important;
            transform:translateY(-1px);
        }

        /* ── Cards (st.container with border) ── */
        [data-testid="stVerticalBlockBorderWrapper"]{
            background:rgba(4,18,42,0.55) !important;
            backdrop-filter:blur(14px) saturate(1.4) !important;
            border:1px solid rgba(0,180,255,0.18) !important;
            border-radius:16px !important;
            box-shadow:0 4px 30px rgba(0,0,0,0.4), 0 0 1px rgba(0,180,255,0.3) !important;
            overflow:hidden;
            transition:border-color .35s, box-shadow .35s, transform .25s;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:hover{
            border-color:rgba(0,200,255,0.45) !important;
            box-shadow:0 8px 40px rgba(0,0,0,0.5), 0 0 20px rgba(0,200,255,0.12) !important;
            transform:translateY(-3px);
        }

        /* ── Subheader inside cards ── */
        [data-testid="stVerticalBlockBorderWrapper"] h3,
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stSubheader"]{
            font-family:'Inter',sans-serif !important;
            font-weight:600 !important;
            color:#e0f4ff !important;
            font-size:1.05rem !important;
            border-bottom:1px solid rgba(0,180,255,0.12);
            padding-bottom:8px;
            margin-bottom:8px;
        }

        /* ── Badges ── */
        .badgebar{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 10px;align-items:center}
        .badge{
            display:inline-flex;align-items:center;gap:5px;
            padding:5px 14px;
            border-radius:999px;
            font-size:0.82rem;font-weight:500;
            font-family:'Inter',sans-serif;
            line-height:1.3;
            backdrop-filter:blur(4px);
            transition:transform .2s, box-shadow .2s;
        }
        .badge:hover{transform:scale(1.04);box-shadow:0 0 10px rgba(0,180,255,0.2)}
        .badge-platform{
            background:rgba(0,140,255,0.15);
            border:1px solid rgba(0,180,255,0.35);
            color:#b8e8ff;
        }
        .badge-seller{
            background:rgba(0,255,200,0.08);
            border:1px solid rgba(0,255,180,0.25);
            color:#a8f0d8;
        }
        .badge-brand{
            background:rgba(180,120,255,0.10);
            border:1px solid rgba(180,140,255,0.30);
            color:#d4c0ff;
        }
        .badge-custom{
            border:1px solid;
            font-weight:600;
        }

        /* ── Price ── */
        .price-tag{
            font-family:'JetBrains Mono','Inter',monospace;
            font-size:1.35rem;font-weight:700;
            color:#00e8ff;
            text-shadow:0 0 12px rgba(0,220,255,0.35);
            margin:6px 0 4px;
            letter-spacing:0.5px;
        }
        .price-unavailable{
            font-size:0.88rem;color:rgba(180,200,220,0.5);
            font-style:italic;margin:6px 0 4px;
        }

        /* ── Image container ── */
        .img-wrap{
            border-radius:10px;overflow:hidden;
            border:1px solid rgba(0,180,255,0.12);
            margin-bottom:10px;
            background:rgba(0,10,30,0.4);
        }
        .img-wrap img{
            width:100%;height:auto;
            object-fit:contain;
            max-height:260px;
        }

        /* ── Link button ── */
        .link-btn{
            display:inline-block;
            background:linear-gradient(135deg, rgba(0,100,220,0.20), rgba(0,180,255,0.10));
            border:1px solid rgba(0,200,255,0.30);
            border-radius:8px;
            padding:6px 16px;
            color:#b0e4ff !important;
            font-size:0.85rem;font-weight:500;
            text-decoration:none !important;
            font-family:'Inter',sans-serif;
            transition:all .25s;
        }
        .link-btn:hover{
            background:linear-gradient(135deg, rgba(0,120,240,0.35), rgba(0,200,255,0.22));
            border-color:rgba(0,230,255,0.7);
            box-shadow:0 0 14px rgba(0,200,255,0.18);
            color:#e0f8ff !important;
        }

        /* ── Expander ── */
        [data-testid="stExpander"]{
            border:1px solid rgba(0,160,255,0.12) !important;
            border-radius:10px !important;
            background:rgba(0,15,40,0.3) !important;
        }
        [data-testid="stExpander"] summary{
            font-family:'Inter',sans-serif !important;
            font-weight:500 !important;
            color:#90d0ff !important;
        }

        /* ── Spinner ── */
        [data-testid="stSpinner"]{color:#00c8ff !important}

        /* ── Result count ── */
        .result-count{
            text-align:center;
            font-size:0.92rem;
            color:rgba(0,200,255,0.55);
            margin:8px 0 18px;
            letter-spacing:1px;
            font-family:'JetBrains Mono','Inter',monospace;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _platform_badge_html(platform: str) -> str:
    colors = _PLATFORM_COLORS.get(platform)
    if colors:
        fg, _ = colors
        return (
            f"<span class='badge badge-custom' "
            f"style='color:{fg};border-color:{fg};background:rgba(255,255,255,0.04)'>"
            f"{platform}</span>"
        )
    return f"<span class='badge badge-platform'>{platform}</span>"


def _render_card(r: dict, idx: int) -> None:
    name = r.get("name") or "Unknown product"
    image_url = (r.get("image_url") or "").strip()
    platform_text = (r.get("platform") or "").strip() or "Unknown"
    seller_text = (r.get("seller") or "").strip()
    brand_text = ""
    for reason in r.get("reasons", []):
        if "brand:" in reason.lower():
            brand_text = reason.split(":")[-1].strip().rstrip(".")
            break
    price_raw = r.get("price") or ""
    url = r.get("url") or ""

    st.subheader(f"{idx}. {_truncate(name, 68)}")

    if image_url:
        st.markdown(
            f'<div class="img-wrap"><img src="{image_url}" alt="product"></div>',
            unsafe_allow_html=True,
        )

    badges = _platform_badge_html(platform_text)
    if seller_text:
        badges += f"<span class='badge badge-seller'>{_truncate(seller_text, 30)}</span>"
    if brand_text:
        badges += f"<span class='badge badge-brand'>{_truncate(brand_text, 26)}</span>"
    st.markdown(f'<div class="badgebar">{badges}</div>', unsafe_allow_html=True)

    if price_raw and "unavailable" not in price_raw.lower():
        st.markdown(f'<div class="price-tag">{price_raw}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="price-unavailable">Price unavailable</div>', unsafe_allow_html=True)

    if url:
        st.markdown(
            f'<a class="link-btn" href="{url}" target="_blank" rel="noopener">'
            f'View on {platform_text} &rarr;</a>',
            unsafe_allow_html=True,
        )

    with st.expander("Details & evidence", expanded=False):
        for reason in r.get("reasons", []):
            st.write(f"- {reason}")
        if r.get("evidence"):
            st.markdown("---")
            for field, value in r.get("evidence", []):
                st.code(f"{field}: {str(value)[:120]}", language=None)


def main():
    st.set_page_config(page_title="SKU Check — Smart Product Search", layout="wide")
    _inject_tech_css()

    st.markdown(
        '<h1 style="text-align:center;margin-bottom:0">SKU Check</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="text-align:center;color:rgba(0,200,255,0.5);font-size:0.92rem;'
        'letter-spacing:2px;margin-top:2px;font-family:JetBrains Mono,monospace">'
        'INTELLIGENT PRODUCT DISCOVERY ENGINE</p>',
        unsafe_allow_html=True,
    )

    user_input = st.text_area(
        "Describe what you are looking for:",
        height=100,
        placeholder="e.g., Wireless headphones under $100 for running, noise cancellation preferred",
    )

    col_left, col_center, col_right = st.columns([1, 1, 1])
    with col_center:
        search_clicked = st.button("Search", use_container_width=True)

    if search_clicked:
        if not (user_input or "").strip():
            st.warning("Please enter a description of what you want.")
            return
        with st.spinner("Scanning product sources..."):
            results = run_pipeline(user_input.strip())
        if not results:
            intent = extract_intent(user_input.strip())
            results = get_demo_results(user_input.strip(), intent.keywords)
            if results:
                st.info("Direct search returned no results. Showing recommended retailers.")
        if not results:
            st.warning("No results available. Check your network connection and try again.")
            return

        st.markdown(
            f'<div class="result-count">// {len(results)} PRODUCT{"S" if len(results) != 1 else ""} FOUND //</div>',
            unsafe_allow_html=True,
        )

        for i in range(0, len(results), 2):
            row_cols = st.columns(2)
            for col_i in range(2):
                idx = i + col_i
                if idx >= len(results):
                    continue
                with row_cols[col_i]:
                    with st.container(border=True):
                        _render_card(results[idx], idx + 1)


if __name__ == "__main__":
    main()
