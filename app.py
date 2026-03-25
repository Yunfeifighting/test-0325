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
    "Amazon": "#ff9900",
    "Walmart": "#0071dc",
    "Target": "#cc0000",
    "Best Buy": "#0046be",
    "eBay": "#e53238",
    "Costco": "#e31837",
    "Newegg": "#f36c21",
    "The Home Depot": "#f96302",
    "Lowe's": "#004990",
}

_PLACEHOLDER_IMG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='300'"
    " fill='none'%3E%3Crect width='400' height='300' rx='16' fill='%23101828'/%3E"
    "%3Ctext x='50%25' y='48%25' text-anchor='middle' fill='%234a5578' font-size='42'"
    " font-family='system-ui'%3E%F0%9F%93%A6%3C/text%3E"
    "%3Ctext x='50%25' y='62%25' text-anchor='middle' fill='%233a4560' font-size='14'"
    " font-family='system-ui'%3ENo image available%3C/text%3E%3C/svg%3E"
)


def _inject_tech_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

        @keyframes aurora{
            0%  {background-position:0% 50%}
            50% {background-position:100% 50%}
            100%{background-position:0% 50%}
        }
        @keyframes float-orb{
            0%,100%{transform:translate(0,0) scale(1)}
            33%{transform:translate(40px,-25px) scale(1.1)}
            66%{transform:translate(-30px,20px) scale(0.92)}
        }
        @keyframes scan{
            0%{top:-15%}
            100%{top:115%}
        }
        @keyframes border-pulse{
            0%,100%{border-color:rgba(0,200,255,0.12)}
            50%{border-color:rgba(100,80,240,0.28)}
        }
        @keyframes hud-blink{
            0%,90%,100%{opacity:0.5}
            95%{opacity:1}
        }

        /* ── Base ── */
        html, body, [data-testid="stAppViewContainer"]{
            background:
                radial-gradient(ellipse 1000px 700px at 12% 18%, rgba(100,50,200,0.20), transparent),
                radial-gradient(ellipse 800px 550px at 78% 12%, rgba(0,160,255,0.15), transparent),
                radial-gradient(ellipse 650px 450px at 45% 82%, rgba(220,60,180,0.11), transparent),
                radial-gradient(ellipse 550px 550px at 92% 65%, rgba(0,240,210,0.09), transparent),
                linear-gradient(160deg, #04060c 0%, #080d1a 30%, #060a16 60%, #040710 100%);
            background-size: 200% 200%;
            animation: aurora 22s ease infinite;
            color: #d0dce8;
            font-family: 'Inter', -apple-system, sans-serif;
        }
        [data-testid="stHeader"]{background:transparent !important}

        /* ── Floating orbs ── */
        [data-testid="stAppViewContainer"]::before,
        [data-testid="stAppViewContainer"]::after{
            content:'';position:fixed;border-radius:50%;pointer-events:none;z-index:0;
        }
        [data-testid="stAppViewContainer"]::before{
            width:600px;height:600px;top:-120px;left:-150px;
            background:radial-gradient(circle, rgba(100,40,220,0.25), transparent 65%);
            filter:blur(90px);
            animation:float-orb 16s ease-in-out infinite;
        }
        [data-testid="stAppViewContainer"]::after{
            width:500px;height:500px;bottom:-80px;right:-120px;
            background:radial-gradient(circle, rgba(0,200,255,0.18), transparent 65%);
            filter:blur(85px);
            animation:float-orb 20s ease-in-out infinite reverse;
        }
        [data-testid="stAppViewContainer"] > *{position:relative;z-index:1}

        /* ── Scan line ── */
        .scan-overlay{
            position:fixed;left:0;width:100%;height:3px;pointer-events:none;z-index:999;
            background:linear-gradient(90deg, transparent 5%, rgba(0,200,255,0.35) 50%, transparent 95%);
            box-shadow:0 0 20px 4px rgba(0,200,255,0.10);
            animation:scan 6s linear infinite;
            opacity:0.5;
        }

        /* ── Grid dot pattern ── */
        .dot-grid{
            position:fixed;inset:0;pointer-events:none;z-index:0;
            background-image:radial-gradient(rgba(100,140,255,0.07) 1px, transparent 1px);
            background-size:32px 32px;
        }

        /* ── Title ── */
        [data-testid="stAppViewContainer"] h1{
            font-family:'Orbitron','Inter',sans-serif !important;
            font-weight:800 !important;
            font-size:2.4rem !important;
            background:linear-gradient(135deg, #a78bfa 0%, #38bdf8 35%, #34d399 65%, #c084fc 100%);
            background-size:300% auto;
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            animation:aurora 7s linear infinite;
            letter-spacing:2px;
            text-align:center;
            text-transform:uppercase;
        }

        /* ── Subtitle ── */
        .subtitle{
            text-align:center;
            font-size:0.75rem;font-weight:500;
            letter-spacing:5px;text-transform:uppercase;
            color:rgba(0,200,255,0.40);
            font-family:'JetBrains Mono',monospace;
            margin:-2px 0 30px;
            animation:hud-blink 4s ease infinite;
        }

        /* ── Search area wrapper ── */
        .search-wrap{
            max-width:560px;
            margin:0 auto 6px;
        }

        /* ── Search input ── */
        textarea, [data-testid="stTextArea"] textarea{
            background:rgba(8,12,28,0.75) !important;
            border:1px solid rgba(0,180,255,0.18) !important;
            border-radius:12px !important;
            color:#c8d8e8 !important;
            font-family:'Inter',sans-serif !important;
            font-size:0.9rem !important;
            backdrop-filter:blur(14px);
            transition:border-color .3s, box-shadow .3s;
            animation:border-pulse 5s ease infinite;
        }
        textarea:focus, [data-testid="stTextArea"] textarea:focus{
            border-color:rgba(100,80,255,0.50) !important;
            box-shadow:0 0 28px rgba(100,60,220,0.14), 0 0 8px rgba(0,200,255,0.08) !important;
            animation:none;
        }

        /* ── Search button ── */
        .stButton>button{
            background:linear-gradient(135deg, rgba(80,40,200,0.35), rgba(0,160,255,0.22)) !important;
            border:1px solid rgba(0,200,255,0.30) !important;
            border-radius:12px !important;
            color:#c0e8ff !important;
            font-weight:600 !important;
            font-family:'Orbitron','Inter',sans-serif !important;
            font-size:0.85rem !important;
            padding:0.55rem 2rem !important;
            letter-spacing:2px;text-transform:uppercase;
            transition:all .35s cubic-bezier(.4,0,.2,1);
        }
        .stButton>button:hover{
            background:linear-gradient(135deg, rgba(100,60,240,0.50), rgba(0,200,255,0.35)) !important;
            border-color:rgba(0,220,255,0.65) !important;
            box-shadow:0 0 36px rgba(0,200,255,0.20), 0 0 12px rgba(100,60,220,0.15) !important;
            transform:translateY(-2px);
        }

        /* ── HUD card wrapper (applied to st.container border) ── */
        [data-testid="stVerticalBlockBorderWrapper"]{
            background:rgba(8,12,26,0.50) !important;
            backdrop-filter:blur(18px) saturate(1.4) !important;
            border:1px solid rgba(0,180,255,0.12) !important;
            border-radius:16px !important;
            box-shadow:0 4px 32px rgba(0,0,0,0.4) !important;
            overflow:hidden;
            transition:border-color .4s, box-shadow .4s, transform .3s;
            position:relative;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:hover{
            border-color:rgba(0,200,255,0.32) !important;
            box-shadow:0 8px 48px rgba(0,0,0,0.5), 0 0 24px rgba(0,180,255,0.08) !important;
            transform:translateY(-3px);
        }

        /* ── HUD corners ── */
        .hud-corner{
            position:absolute;width:18px;height:18px;pointer-events:none;z-index:2;
        }
        .hud-tl{top:6px;left:6px;border-top:2px solid rgba(0,200,255,0.40);border-left:2px solid rgba(0,200,255,0.40)}
        .hud-tr{top:6px;right:6px;border-top:2px solid rgba(0,200,255,0.40);border-right:2px solid rgba(0,200,255,0.40)}
        .hud-bl{bottom:6px;left:6px;border-bottom:2px solid rgba(0,200,255,0.40);border-left:2px solid rgba(0,200,255,0.40)}
        .hud-br{bottom:6px;right:6px;border-bottom:2px solid rgba(0,200,255,0.40);border-right:2px solid rgba(0,200,255,0.40)}

        /* ── Card title ── */
        .card-title{
            font-family:'Inter',sans-serif;
            font-weight:600;font-size:1rem;
            color:#e4eaf0;
            line-height:1.4;
            margin:0 0 10px;
            display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
        }

        /* ── Badges ── */
        .badgebar{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 10px;align-items:center}
        .badge{
            display:inline-flex;align-items:center;gap:4px;
            padding:4px 11px;
            border-radius:6px;
            font-size:0.76rem;font-weight:500;
            font-family:'JetBrains Mono','Inter',monospace;
            line-height:1.2;
            backdrop-filter:blur(4px);
            transition:transform .2s;
        }
        .badge:hover{transform:translateY(-1px)}
        .badge-platform{
            background:rgba(0,160,255,0.12);
            border:1px solid rgba(0,200,255,0.25);
            color:#a0d8f8;
        }
        .badge-seller{
            background:rgba(0,220,180,0.08);
            border:1px solid rgba(0,220,180,0.20);
            color:#80e0cc;
        }
        .badge-brand{
            background:rgba(180,120,255,0.08);
            border:1px solid rgba(180,140,255,0.20);
            color:#c8b0f0;
        }
        .badge-custom{border:1px solid;font-weight:600}

        /* ── Price ── */
        .price-row{display:flex;align-items:baseline;gap:8px;margin:2px 0 12px}
        .price-tag{
            font-family:'Orbitron','JetBrains Mono',monospace;
            font-size:1.3rem;font-weight:700;
            color:#00e0ff;
            text-shadow:0 0 14px rgba(0,220,255,0.30);
        }
        .price-unavailable{
            font-size:0.80rem;
            color:rgba(140,150,170,0.40);
            font-style:italic;
        }

        /* ── Link button ── */
        .link-btn{
            display:inline-flex;align-items:center;gap:6px;
            background:linear-gradient(135deg, rgba(0,120,220,0.15), rgba(0,200,255,0.08));
            border:1px solid rgba(0,200,255,0.22);
            border-radius:8px;
            padding:7px 18px;
            color:#90d4f0 !important;
            font-size:0.80rem;font-weight:500;
            text-decoration:none !important;
            font-family:'JetBrains Mono','Inter',monospace;
            letter-spacing:0.5px;
            transition:all .3s cubic-bezier(.4,0,.2,1);
        }
        .link-btn:hover{
            background:linear-gradient(135deg, rgba(0,140,240,0.28), rgba(0,220,255,0.18));
            border-color:rgba(0,220,255,0.55);
            box-shadow:0 0 18px rgba(0,200,255,0.12);
            color:#d0f0ff !important;
            transform:translateY(-1px);
        }
        .link-btn svg{width:13px;height:13px;fill:currentColor;opacity:0.6}

        /* ── Product image (st.image) ── */
        [data-testid="stImage"]{
            border-radius:10px;
            overflow:hidden;
            border:1px solid rgba(0,180,255,0.10);
            background:rgba(6,10,22,0.6);
        }
        [data-testid="stImage"] img{
            object-fit:contain !important;
            max-height:240px !important;
        }
        [data-testid="stImage"]:hover img{
            transform:scale(1.03);
            transition:transform .4s ease;
        }

        /* ── Expander ── */
        [data-testid="stExpander"]{
            border:1px solid rgba(0,160,255,0.08) !important;
            border-radius:10px !important;
            background:rgba(6,10,22,0.30) !important;
        }
        [data-testid="stExpander"] summary{
            font-family:'JetBrains Mono','Inter',monospace !important;
            font-weight:500 !important;
            color:rgba(0,200,255,0.45) !important;
            font-size:0.82rem !important;
            letter-spacing:0.5px;
        }

        /* ── Result count ── */
        .result-count{
            text-align:center;
            font-size:0.78rem;
            color:rgba(0,200,255,0.35);
            margin:14px 0 24px;
            letter-spacing:3px;
            font-family:'Orbitron','JetBrains Mono',monospace;
            text-transform:uppercase;
        }

        /* ── Divider ── */
        .divider{
            height:1px;margin:12px 0;
            background:linear-gradient(90deg, transparent, rgba(0,180,255,0.12), transparent);
        }
        </style>

        <div class="dot-grid"></div>
        <div class="scan-overlay"></div>
        """,
        unsafe_allow_html=True,
    )


def _platform_badge_html(platform: str) -> str:
    color = _PLATFORM_COLORS.get(platform)
    if color:
        return (
            f"<span class='badge badge-custom' "
            f"style='color:{color};border-color:{color}40;background:{color}12'>"
            f"{platform}</span>"
        )
    return f"<span class='badge badge-platform'>{platform}</span>"


def _render_card(r: dict, idx: int) -> None:
    """Render a single product card using Streamlit native + HTML hybrid."""
    name = r.get("name") or "Unknown product"
    image_url = (r.get("image_url") or "").strip()
    platform_text = (r.get("platform") or "").strip() or "Unknown"
    seller_text = (r.get("seller") or "").strip()
    price_raw = r.get("price") or ""
    url = r.get("url") or ""

    brand_text = ""
    for reason in r.get("reasons", []):
        if "brand:" in reason.lower():
            brand_text = reason.split(":")[-1].strip().rstrip(".")
            break

    with st.container(border=True):
        st.markdown(
            '<div class="hud-corner hud-tl"></div><div class="hud-corner hud-tr"></div>'
            '<div class="hud-corner hud-bl"></div><div class="hud-corner hud-br"></div>',
            unsafe_allow_html=True,
        )

        if image_url:
            st.image(image_url, use_container_width=True)

        st.markdown(
            f'<div class="card-title">{idx}. {_truncate(name, 72)}</div>',
            unsafe_allow_html=True,
        )

        badges = _platform_badge_html(platform_text)
        if seller_text:
            badges += f"<span class='badge badge-seller'>{_truncate(seller_text, 28)}</span>"
        if brand_text:
            badges += f"<span class='badge badge-brand'>{_truncate(brand_text, 24)}</span>"
        st.markdown(f'<div class="badgebar">{badges}</div>', unsafe_allow_html=True)

        if price_raw and "unavailable" not in price_raw.lower():
            st.markdown(f'<div class="price-row"><span class="price-tag">{price_raw}</span></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="price-row"><span class="price-unavailable">Price unavailable</span></div>', unsafe_allow_html=True)

        if url:
            arrow = (
                '<svg viewBox="0 0 20 20"><path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 '
                '101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"/>'
                '<path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 '
                '10-2 0v3H5V7h3a1 1 0 000-2H5z"/></svg>'
            )
            st.markdown(
                f'<a class="link-btn" href="{url}" target="_blank" rel="noopener">'
                f'View on {platform_text} {arrow}</a>',
                unsafe_allow_html=True,
            )

        with st.expander("// DETAILS", expanded=False):
            for reason in r.get("reasons", []):
                st.write(f"- {reason}")
            if r.get("evidence"):
                st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
                for fld, val in r.get("evidence", []):
                    st.code(f"{fld}: {str(val)[:120]}", language=None)


def main():
    st.set_page_config(page_title="SKU Check — Smart Product Search", layout="wide")
    _inject_tech_css()

    st.markdown('<h1>SKU Check</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="subtitle">Intelligent Product Discovery Engine</p>',
        unsafe_allow_html=True,
    )

    _, search_col, _ = st.columns([1, 2, 1])
    with search_col:
        user_input = st.text_area(
            "Describe what you are looking for:",
            height=72,
            placeholder="e.g., Wireless headphones under $100, noise cancellation",
        )
        search_clicked = st.button("SEARCH", use_container_width=True)

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
            f'<div class="result-count">// {len(results)} TARGET{"S" if len(results) != 1 else ""} ACQUIRED //</div>',
            unsafe_allow_html=True,
        )

        for i in range(0, len(results), 2):
            row_cols = st.columns(2)
            for col_i in range(2):
                idx = i + col_i
                if idx >= len(results):
                    continue
                with row_cols[col_i]:
                    _render_card(results[idx], idx + 1)


if __name__ == "__main__":
    main()
