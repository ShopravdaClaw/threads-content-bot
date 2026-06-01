from playwright.sync_api import sync_playwright
import json

urls = [
    'https://www.threads.com/',
    'https://www.threads.com/@threads',
    'https://www.threads.com/search?q=twitch'
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    results = []
    for url in urls:
        item = {'url': url}
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=45000)
            page.wait_for_timeout(3000)
            item['title'] = page.title()
            item['text_sample'] = page.locator('body').inner_text()[:2000]
            item['final_url'] = page.url
        except Exception as e:
            item['error'] = str(e)
        results.append(item)
    browser.close()
print(json.dumps(results, ensure_ascii=False, indent=2))
