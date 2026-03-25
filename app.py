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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

        @keyframes aurora{
            0%  {background-position:0% 50%}
            50% {background-position:100% 50%}
            100%{background-position:0% 50%}
        }
        @keyframes float-orb{
            0%,100%{transform:translate(0,0) scale(1)}
            33%{transform:translate(30px,-20px) scale(1.08)}
            66%{transform:translate(-20px,15px) scale(0.95)}
        }
        @keyframes shimmer{
            0%{background-position:-200% 0}
            100%{background-position:200% 0}
        }
        @keyframes breathe{
            0%,100%{opacity:0.6}
            50%{opacity:1}
        }

        /* ── Base: deep space + aurora wash ── */
        html, body, [data-testid="stAppViewContainer"]{
            background:
                radial-gradient(ellipse 900px 600px at 15% 20%, rgba(120,80,220,0.18), transparent),
                radial-gradient(ellipse 700px 500px at 75% 15%, rgba(0,180,255,0.13), transparent),
                radial-gradient(ellipse 600px 400px at 50% 80%, rgba(200,80,180,0.10), transparent),
                radial-gradient(ellipse 500px 500px at 90% 70%, rgba(0,220,200,0.08), transparent),
                linear-gradient(160deg, #06080f 0%, #0a0e1a 30%, #080c18 60%, #050810 100%);
            background-size: 200% 200%;
            animation: aurora 25s ease infinite;
            color: #d8e4f0;
            font-family: 'Inter', -apple-system, sans-serif;
        }
        [data-testid="stHeader"]{background:transparent !important}

        /* ── Floating orbs (decorative) ── */
        [data-testid="stAppViewContainer"]::before,
        [data-testid="stAppViewContainer"]::after{
            content:'';position:fixed;border-radius:50%;pointer-events:none;z-index:0;
            filter:blur(80px);
        }
        [data-testid="stAppViewContainer"]::before{
            width:500px;height:500px;top:-80px;left:-100px;
            background:radial-gradient(circle, rgba(100,60,220,0.22), transparent 70%);
            animation:float-orb 18s ease-in-out infinite;
        }
        [data-testid="stAppViewContainer"]::after{
            width:420px;height:420px;bottom:-60px;right:-80px;
            background:radial-gradient(circle, rgba(0,200,240,0.16), transparent 70%);
            animation:float-orb 22s ease-in-out infinite reverse;
        }
        [data-testid="stAppViewContainer"] > *{position:relative;z-index:1}

        /* ── Title ── */
        [data-testid="stAppViewContainer"] h1{
            font-family:'Inter',sans-serif !important;
            font-weight:700 !important;
            font-size:2.6rem !important;
            background:linear-gradient(135deg, #a78bfa 0%, #60a5fa 30%, #34d399 60%, #a78bfa 100%);
            background-size:300% auto;
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            animation:aurora 8s linear infinite;
            letter-spacing:-0.5px;
            text-align:center;
        }

        /* ── Subtitle ── */
        .subtitle{
            text-align:center;
            font-size:0.88rem;font-weight:400;
            letter-spacing:3px;
            color:rgba(168,162,220,0.55);
            font-family:'JetBrains Mono',monospace;
            margin:-4px 0 28px;
        }

        /* ── Search input ── */
        textarea, [data-testid="stTextArea"] textarea{
            background:rgba(14,18,36,0.70) !important;
            border:1px solid rgba(140,120,220,0.20) !important;
            border-radius:14px !important;
            color:#d0dce8 !important;
            font-family:'Inter',sans-serif !important;
            font-size:0.95rem !important;
            backdrop-filter:blur(12px);
            transition:border-color .3s, box-shadow .3s;
        }
        textarea:focus, [data-testid="stTextArea"] textarea:focus{
            border-color:rgba(140,120,255,0.50) !important;
            box-shadow:0 0 24px rgba(120,80,220,0.12), 0 0 8px rgba(0,180,255,0.08) !important;
        }

        /* ── Search button ── */
        .stButton>button{
            background:linear-gradient(135deg, rgba(100,60,220,0.30), rgba(0,160,240,0.20)) !important;
            border:1px solid rgba(140,120,255,0.30) !important;
            border-radius:14px !important;
            color:#d4d0f8 !important;
            font-weight:600 !important;
            font-family:'Inter',sans-serif !important;
            font-size:0.95rem !important;
            padding:0.65rem 2.8rem !important;
            letter-spacing:0.8px;
            transition:all .35s cubic-bezier(.4,0,.2,1);
        }
        .stButton>button:hover{
            background:linear-gradient(135deg, rgba(120,80,240,0.45), rgba(0,180,255,0.30)) !important;
            border-color:rgba(160,140,255,0.60) !important;
            box-shadow:0 0 32px rgba(120,80,220,0.20), 0 4px 16px rgba(0,0,0,0.3) !important;
            transform:translateY(-2px);
        }

        /* ── Product card ── */
        .product-card{
            background:rgba(12,16,32,0.55);
            backdrop-filter:blur(20px) saturate(1.5);
            border:1px solid rgba(120,100,200,0.14);
            border-radius:20px;
            overflow:hidden;
            transition:border-color .4s, box-shadow .4s, transform .3s;
            margin-bottom:4px;
        }
        .product-card:hover{
            border-color:rgba(140,120,255,0.35);
            box-shadow:
                0 12px 48px rgba(0,0,0,0.45),
                0 0 30px rgba(120,80,220,0.10),
                inset 0 1px 0 rgba(255,255,255,0.04);
            transform:translateY(-4px);
        }

        /* ── Card image ── */
        .card-img-wrap{
            position:relative;
            background:linear-gradient(135deg, rgba(10,14,28,0.9), rgba(16,20,40,0.9));
            display:flex;align-items:center;justify-content:center;
            min-height:200px;max-height:280px;
            overflow:hidden;
        }
        .card-img-wrap::after{
            content:'';position:absolute;inset:0;
            background:linear-gradient(180deg, transparent 60%, rgba(12,16,32,0.95) 100%);
            pointer-events:none;
        }
        .card-img-wrap img{
            width:100%;height:100%;
            object-fit:contain;
            max-height:280px;
            padding:12px;
            transition:transform .4s cubic-bezier(.4,0,.2,1);
        }
        .product-card:hover .card-img-wrap img{
            transform:scale(1.05);
        }

        /* ── Card body ── */
        .card-body{padding:18px 20px 20px;}

        .card-title{
            font-family:'Inter',sans-serif;
            font-weight:600;font-size:1.02rem;
            color:#e8edf4;
            line-height:1.4;
            margin:0 0 10px;
            display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
        }

        /* ── Badges ── */
        .badgebar{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px;align-items:center}
        .badge{
            display:inline-flex;align-items:center;gap:4px;
            padding:4px 12px;
            border-radius:8px;
            font-size:0.78rem;font-weight:500;
            font-family:'Inter',sans-serif;
            line-height:1.2;
            backdrop-filter:blur(4px);
            transition:transform .2s;
        }
        .badge:hover{transform:translateY(-1px)}
        .badge-platform{
            background:rgba(100,80,200,0.15);
            border:1px solid rgba(140,120,255,0.25);
            color:#c4b8f0;
        }
        .badge-seller{
            background:rgba(0,200,180,0.08);
            border:1px solid rgba(0,200,180,0.20);
            color:#90e0d0;
        }
        .badge-brand{
            background:rgba(200,140,255,0.08);
            border:1px solid rgba(200,160,255,0.20);
            color:#d0b8f0;
        }
        .badge-custom{
            border:1px solid;
            font-weight:600;
        }

        /* ── Price ── */
        .price-row{display:flex;align-items:baseline;gap:8px;margin:0 0 14px}
        .price-tag{
            font-family:'JetBrains Mono','Inter',monospace;
            font-size:1.4rem;font-weight:700;
            background:linear-gradient(135deg, #60a5fa, #a78bfa);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
        }
        .price-unavailable{
            font-size:0.82rem;
            color:rgba(160,170,190,0.40);
            font-style:italic;
        }

        /* ── Link button ── */
        .link-btn{
            display:inline-flex;align-items:center;gap:6px;
            background:linear-gradient(135deg, rgba(100,60,220,0.18), rgba(0,160,240,0.12));
            border:1px solid rgba(140,120,255,0.22);
            border-radius:10px;
            padding:8px 20px;
            color:#b8b0e8 !important;
            font-size:0.84rem;font-weight:500;
            text-decoration:none !important;
            font-family:'Inter',sans-serif;
            transition:all .3s cubic-bezier(.4,0,.2,1);
        }
        .link-btn:hover{
            background:linear-gradient(135deg, rgba(120,80,240,0.30), rgba(0,180,255,0.20));
            border-color:rgba(160,140,255,0.50);
            box-shadow:0 0 20px rgba(120,80,220,0.14);
            color:#e0d8ff !important;
            transform:translateY(-1px);
        }
        .link-btn svg{width:14px;height:14px;fill:currentColor;opacity:0.7}

        /* ── Expander ── */
        [data-testid="stExpander"]{
            border:1px solid rgba(120,100,200,0.10) !important;
            border-radius:12px !important;
            background:rgba(10,14,28,0.35) !important;
        }
        [data-testid="stExpander"] summary{
            font-family:'Inter',sans-serif !important;
            font-weight:500 !important;
            color:rgba(168,160,220,0.70) !important;
            font-size:0.88rem !important;
        }

        /* ── Result count ── */
        .result-count{
            text-align:center;
            font-size:0.82rem;
            color:rgba(140,130,200,0.45);
            margin:12px 0 22px;
            letter-spacing:2px;
            font-family:'JetBrains Mono',monospace;
        }

        /* ── Divider line ── */
        .divider{
            height:1px;margin:14px 0;
            background:linear-gradient(90deg, transparent, rgba(140,120,220,0.15), transparent);
        }
        </style>
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


def _render_card_html(r: dict, idx: int) -> str:
    name = _truncate(r.get("name") or "Unknown product", 80)
    image_url = (r.get("image_url") or "").strip() or _PLACEHOLDER_IMG
    platform_text = (r.get("platform") or "").strip() or "Unknown"
    seller_text = (r.get("seller") or "").strip()
    price_raw = r.get("price") or ""
    url = r.get("url") or ""

    brand_text = ""
    for reason in r.get("reasons", []):
        if "brand:" in reason.lower():
            brand_text = reason.split(":")[-1].strip().rstrip(".")
            break

    badges_html = _platform_badge_html(platform_text)
    if seller_text:
        badges_html += f"<span class='badge badge-seller'>{_truncate(seller_text, 28)}</span>"
    if brand_text:
        badges_html += f"<span class='badge badge-brand'>{_truncate(brand_text, 24)}</span>"

    if price_raw and "unavailable" not in price_raw.lower():
        price_html = f'<span class="price-tag">{price_raw}</span>'
    else:
        price_html = '<span class="price-unavailable">Price unavailable</span>'

    arrow_svg = (
        '<svg viewBox="0 0 20 20"><path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 '
        '101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"/>'
        '<path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 '
        '10-2 0v3H5V7h3a1 1 0 000-2H5z"/></svg>'
    )
    link_html = (
        f'<a class="link-btn" href="{url}" target="_blank" rel="noopener">'
        f'View on {platform_text} {arrow_svg}</a>'
    ) if url else ""

    return f"""
    <div class="product-card">
      <div class="card-img-wrap">
        <img src="{image_url}" alt="{_truncate(name, 40)}" loading="lazy"
             onerror="this.src='{_PLACEHOLDER_IMG}'">
      </div>
      <div class="card-body">
        <div class="card-title">{idx}. {name}</div>
        <div class="badgebar">{badges_html}</div>
        <div class="price-row">{price_html}</div>
        {link_html}
      </div>
    </div>
    """


def main():
    st.set_page_config(page_title="SKU Check — Smart Product Search", layout="wide")
    _inject_tech_css()

    st.markdown('<h1>SKU Check</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="subtitle">INTELLIGENT PRODUCT DISCOVERY</p>',
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
            f'<div class="result-count">{len(results)} PRODUCT{"S" if len(results) != 1 else ""} FOUND</div>',
            unsafe_allow_html=True,
        )

        for i in range(0, len(results), 2):
            row_cols = st.columns(2)
            for col_i in range(2):
                idx = i + col_i
                if idx >= len(results):
                    continue
                r = results[idx]
                with row_cols[col_i]:
                    st.markdown(
                        _render_card_html(r, idx + 1),
                        unsafe_allow_html=True,
                    )
                    with st.expander("Details & evidence", expanded=False):
                        for reason in r.get("reasons", []):
                            st.write(f"- {reason}")
                        if r.get("evidence"):
                            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
                            for fld, val in r.get("evidence", []):
                                st.code(f"{fld}: {str(val)[:120]}", language=None)


if __name__ == "__main__":
    main()
