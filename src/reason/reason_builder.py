"""Build 3-5 traceable recommendation reasons from extracted product fields."""
from typing import List, Optional

from src.extract.product_extractor import ProductInfo


def _fmt_price(p: ProductInfo) -> str | None:
    if p.price is not None and p.currency:
        return f"{p.currency} {p.price:.2f}"
    return None


def build_reasons(
    product: ProductInfo,
    user_keywords: List[str],
    budget_min: Optional[float] = None,
    budget_max: Optional[float] = None,
) -> List[dict]:
    """Return 3-5 reasons, each with 'text' and 'evidence' (field path + value)."""
    reasons: List[dict] = []
    ev = product.raw_fields.copy()

    if product.name:
        reasons.append({
            "text": f"Product matches your search: {product.name[:80]}{'...' if len(product.name) > 80 else ''}.",
            "evidence": ("name", product.name),
        })
    if product.price is not None and product.currency == "USD":
        price_str = _fmt_price(product)
        reasons.append({
            "text": f"Clear USD pricing: {price_str}.",
            "evidence": ("offers.price", str(product.price)),
        })
        if budget_max is not None and product.price <= budget_max * 1.1:
            reasons.append({
                "text": f"Within your budget (under ${budget_max:.0f}).",
                "evidence": ("price_budget_match", str(product.price)),
            })
        elif budget_min is not None and product.price >= budget_min * 0.9:
            hi = budget_max if budget_max is not None else budget_min * 2
            reasons.append({
                "text": f"Fits your price range (around ${budget_min:.0f}-${hi:.0f}).",
                "evidence": ("price_range", str(product.price)),
            })
    if product.brand:
        reasons.append({
            "text": f"From established brand: {product.brand}.",
            "evidence": ("brand", product.brand),
        })
    if product.platform:
        reasons.append({
            "text": f"Available on platform: {product.platform}.",
            "evidence": ("platform", product.platform),
        })
    if product.seller:
        reasons.append({
            "text": f"Seller/store identified: {product.seller}.",
            "evidence": ("seller", product.seller),
        })
    if product.description and len(product.description) > 20:
        desc = product.description[:120].strip() + ("..." if len(product.description) > 120 else "")
        reasons.append({
            "text": f"Key details: {desc}.",
            "evidence": ("description", product.description[:200]),
        })
    for k, v in ev.items():
        if k in ("name", "brand", "description", "price", "offers"):
            continue
        if isinstance(v, str) and len(v) > 3 and len(reasons) < 5:
            reasons.append({
                "text": f"{k.replace('_', ' ').title()}: {v[:60]}{'...' if len(str(v)) > 60 else ''}.",
                "evidence": (k, str(v)[:100]),
            })
        elif isinstance(v, (int, float)) and len(reasons) < 5:
            reasons.append({
                "text": f"{k.replace('_', ' ').title()}: {v}.",
                "evidence": (k, str(v)),
            })
        if len(reasons) >= 5:
            break

    if user_keywords:
        kw_match = ", ".join(user_keywords[:3])
        if len(reasons) < 5:
            reasons.append({
                "text": f"Matches your criteria: {kw_match}.",
                "evidence": ("keywords", kw_match),
            })
    while len(reasons) < 3 and product.url:
        reasons.append({
            "text": "Available from a US-oriented source with reliable shipping.",
            "evidence": ("url", product.url[:80]),
        })
        break
    return reasons[:5]
