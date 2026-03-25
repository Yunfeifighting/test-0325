# US Product Search & Recommendations

Natural language product search for the US market. Enter complex requirements, get matched products with traceable recommendation reasons.

## Setup

1. Install Python 3.10+ from [python.org](https://www.python.org/downloads/) if not installed. Ensure Python is on your PATH.
2. From the project root:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
streamlit run app.py
```

## Deploy (GitHub + Streamlit Community Cloud)

For a **persistent public URL** (`*.streamlit.app`), push this app to GitHub and deploy on [Streamlit Community Cloud](https://streamlit.io/cloud). Step-by-step instructions (Chinese): [DEPLOY_STREAMLIT_CLOUD.zh.md](DEPLOY_STREAMLIT_CLOUD.zh.md).

**Summary:** New app → select repo → **Main file path:** `app.py` → Deploy.

Push this project to your GitHub repo: [GITHUB_PUSH_SKU_CHECK.md](GITHUB_PUSH_SKU_CHECK.md) (or run `push_sku_check.ps1`).

## Usage

1. Open the URL shown in the terminal (e.g. http://localhost:8501).
2. Enter your needs in natural language (e.g., "Wireless headphones under $100 for running").
3. Click **Search** to get product cards with names, prices (USD when available), links, and 3-5 recommendation reasons backed by extracted fields.

## How it works

- **Search**: Scrapes Bing results (US/EN) for candidate URLs.
- **Extract**: Parses JSON-LD Product schema first; falls back to meta tags and page text.
- **Rank**: TF-IDF similarity + budget/price matching.
- **Reasons**: Built from extracted fields only; each reason cites evidence (field + value).
- **Cache**: File-based cache under `.cache/` to avoid repeated fetches.

## Notes

- No API keys required. Uses store search pages (Amazon, etc.) to find products.
- If you see irrelevant results (e.g. search engine pages), delete the `.cache` folder and try again.
- Non-USD prices are labeled; missing prices are marked accordingly.
