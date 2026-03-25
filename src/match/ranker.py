"""Rank candidates by TF-IDF similarity and USD price match."""
from typing import List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.extract.product_extractor import ProductInfo


def _text_for_product(p: ProductInfo) -> str:
    parts = [p.name, p.brand, p.description]
    if p.raw_fields:
        for k, v in p.raw_fields.items():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, (int, float)):
                parts.append(str(v))
    return " ".join(filter(None, parts)).lower()


def rank_products(
    products: List[ProductInfo],
    user_input: str,
    intent_keywords: List[str],
    budget_min: float | None,
    budget_max: float | None,
) -> List[ProductInfo]:
    """Sort products by relevance (TF-IDF + price match)."""
    if not products:
        return []
    query_text = " ".join([user_input] + intent_keywords).lower()
    texts = [_text_for_product(p) for p in products]
    vec = TfidfVectorizer(max_features=500, stop_words="english")
    try:
        mat = vec.fit_transform(texts)
        q_vec = vec.transform([query_text])
        sims = cosine_similarity(q_vec, mat).flatten()
    except Exception:
        sims = [0.5] * len(products)

    def score(i: int) -> float:
        s = float(sims[i]) if i < len(sims) else 0.5
        p = products[i]
        if p.price is not None and (budget_min is not None or budget_max is not None):
            price = p.price
            if budget_max is not None and price > budget_max * 1.2:
                s *= 0.5
            elif budget_min is not None and price < budget_min * 0.5:
                s *= 0.8
            elif budget_min is not None and budget_max is not None:
                if budget_min <= price <= budget_max:
                    s *= 1.2
        return s

    indexed = list(enumerate(products))
    indexed.sort(key=lambda x: -score(x[0]))
    return [p for _, p in indexed]
