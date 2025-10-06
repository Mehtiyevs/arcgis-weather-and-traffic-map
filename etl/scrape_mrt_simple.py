import json
import time
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
OUT_FILE = DATA_DIR / "mrt_announcements.json"
SNAP = DATA_DIR / "mrt_listing_snapshot.html"

BASE = "https://www.mymrt.com.my/traffic-announcement/"
PAGES = 5                            # you said total 5 pages
PAGE_WAIT_MS = 400

def fetch_html(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        ))
        page = ctx.new_page()
        page.set_default_timeout(60000)
        page.goto(url, wait_until="domcontentloaded")
        # gentle scroll to trigger lazy loads
        try:
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(PAGE_WAIT_MS)
        except Exception:
            pass
        html = page.content()
        ctx.close()
        browser.close()
        return html

def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for h5 in soup.find_all("h5"):
        title = h5.get_text(" ", strip=True)
        if not title or len(title) < 5:
            continue

        # Find a reasonable container around the h5 to search for spans/p tags
        container = h5.find_parent(lambda tag: tag.name in ("div", "section", "article"))

        # Dates: find spans with 'text-transform:uppercase' (day/month) and the following year span
        start_date = None
        end_date = None
        if container:
            spans_upper = container.select("span[style*='text-transform:uppercase']")
            spans_year = container.select("span[style*='font-weight:500']")
            try:
                if len(spans_upper) >= 1 and len(spans_year) >= 1:
                    start_date = f"{spans_upper[0].get_text(strip=True)} {spans_year[0].get_text(strip=True)}"
                if len(spans_upper) >= 2 and len(spans_year) >= 2:
                    end_date = f"{spans_upper[1].get_text(strip=True)} {spans_year[1].get_text(strip=True)}"
            except Exception:
                pass

        activity_time = None
        if container:
            at_span = container.select_one("span[style*='text-align:left']")
            if at_span and "Activity Time" in at_span.get_text(" ", strip=True):
                bold = at_span.select_one("span[style*='font-weight:700'], strong")
                if bold:
                    activity_time = bold.get_text(" ", strip=True)
                else:
                    # fallback: full block text
                    activity_time = at_span.get_text(" ", strip=True)

        def extract_after_label(container, label):
            if not container:
                return None
            for p in container.find_all("p"):
                if p.get_text(strip=True).lower() == label.lower():
                    nxt = p.find_next_sibling()
                    if nxt and nxt.name == "p":
                        return nxt.get_text(" ", strip=True)
                    # fallback: next text node
                    nxt_text = p.find_next(string=True)
                    if nxt_text and nxt_text.strip().lower() != label.lower():
                        return nxt_text.strip()
            return None

        description = extract_after_label(container, "Description")
        activity = extract_after_label(container, "Activity")

        # Media Release PDF link (button)
        media_link = None
        if container:
            a_btn = container.select_one("a.button[href$='.pdf'], a.button[href*='wp-content/uploads']")
            if a_btn and a_btn.has_attr("href"):
                media_link = a_btn["href"]

        # Post URL: look for addtoany shortcode data-a2a-url or canonical share link
        post_url = None
        if container:
            addiv = container.select_one("div.addtoany_shortcode")
            if addiv and addiv.has_attr("data-a2a-url"):
                post_url = addiv["data-a2a-url"]
        # fallback: find nearby anchor with the same title text
        if not post_url:
            possible = container.find_all("a", href=True)
            for a in possible:
                if title[:30].lower() in a.get_text(" ", strip=True).lower():
                    post_url = a["href"]; break

        results.append({
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "activity_time": activity_time,
            "description": description,
            "activity": activity,
            "media_release": media_link,
            "post_url": post_url
        })
    return results

def main():
    all_items = []
    for p in range(1, PAGES + 1):
        page_url = BASE if p == 1 else f"{BASE}?sf_paged={p}"
        print(f"[INFO] fetching page {p} -> {page_url}")
        html = fetch_html(page_url)
        if p == 1:
            Path(SNAP).write_text(html, encoding="utf-8")
        items = parse_page(html)
        print(f"[INFO] parsed {len(items)} items from page {p}")
        all_items.extend(items)
        time.sleep(0.5)


    # dedupe by title+post_url
    seen = set()
    unique = []
    for it in all_items:
        sig = (it.get("title"), it.get("post_url"))
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(it)

    OUT_FILE.write_text(json.dumps(unique, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] wrote {len(unique)} announcements -> {OUT_FILE}")

if __name__ == "__main__":
    main()
