from playwright.sync_api import sync_playwright
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path('/home/openclaw/.openclaw/workspace/threads_content_bot')
OUT = BASE / 'trends.json'

SEARCH_QUERIES = [
    {'bucket': 'twitch', 'lang': 'uk', 'query': 'стрім'},
    {'bucket': 'twitch', 'lang': 'uk', 'query': 'твіч'},
    {'bucket': 'twitch', 'lang': 'en', 'query': 'twitch streamer'},
    {'bucket': 'twitch', 'lang': 'en', 'query': 'streamer life'},
    {'bucket': 'nostalgia_2000s', 'lang': 'uk', 'query': 'ностальгія'},
    {'bucket': 'nostalgia_2000s', 'lang': 'en', 'query': '2000s nostalgia'},
    {'bucket': 'zhiza', 'lang': 'uk', 'query': 'жиза'},
    {'bucket': 'zhiza', 'lang': 'en', 'query': 'adulting'},
    {'bucket': 'zhiza', 'lang': 'en', 'query': 'too real'},
    {'bucket': 'gaming_news', 'lang': 'uk', 'query': 'ігри'},
    {'bucket': 'gaming_news', 'lang': 'en', 'query': 'gaming'},
    {'bucket': 'gaming_news', 'lang': 'en', 'query': 'GTA 6'},
    {'bucket': 'gaming_news', 'lang': 'en', 'query': 'CS2'},
    {'bucket': 'toronto_life', 'lang': 'uk', 'query': 'торонто'},
    {'bucket': 'toronto_life', 'lang': 'en', 'query': 'toronto'},
]

FOOTER_MARKERS = [
    'Log in',
    'Continue with Instagram',
    'Threads Terms',
    'Privacy Policy',
    'Cookies Policy',
    'Report a problem',
    'Say more with Threads',
    'Join Threads to share thoughts',
    'See what people are talking about',
    'Log in with username instead',
    '© 2026',
]

DATE_RE = re.compile(r'^\d{2}/\d{2}/\d{2}$')
NUMBER_RE = re.compile(r'^\d+(?:\.\d+)?[KMB]?$', re.IGNORECASE)
SLASH_NUMBER_RE = re.compile(r'^\d+\s*/\s*\d+$')
HANDLE_RE = re.compile(r'^[a-z0-9._]{3,}$', re.IGNORECASE)


def is_footer_line(line: str) -> bool:
    return any(marker in line for marker in FOOTER_MARKERS)


def clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = re.sub(r'\s+', ' ', raw).strip()
        if not line or is_footer_line(line):
            continue
        lines.append(line)
    return lines


def parse_metric(token: str) -> float:
    token = token.strip().upper()
    mult = 1
    if token.endswith('K'):
        mult = 1000
        token = token[:-1]
    elif token.endswith('M'):
        mult = 1_000_000
        token = token[:-1]
    elif token.endswith('B'):
        mult = 1_000_000_000
        token = token[:-1]
    try:
        return float(token) * mult
    except ValueError:
        return 0.0


def engagement_score(metrics: list[str]) -> float:
    values = [parse_metric(x) for x in metrics[:4] if NUMBER_RE.fullmatch(x)]
    if not values:
        return 0.0
    weights = [1.0, 0.6, 1.4, 0.3]
    score = 0.0
    for i, value in enumerate(values):
        score += value * weights[min(i, len(weights) - 1)]
    return score


def infer_style_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags = []
    if '?' in text:
        tags.append('question_hook')
    if '\n' in text or ' / ' in text:
        tags.append('broken_rhythm')
    if any(ch in text for ch in '😂🥲😭😮😄✨💀🤡'):
        tags.append('emoji_punch')
    if any(word in lowered for word in ['я ', 'мені', 'мене', 'мій', 'i ', 'my ', 'me ']):
        tags.append('first_person')
    if any(word in lowered for word in ['remember', 'памʼятаєте', 'памятаєте', 'хто ще', 'nostalgia']):
        tags.append('nostalgia_call')
    if len(text) < 120:
        tags.append('short_hit')
    if 'Translate' in text:
        tags.append('translated')
    return tags


def looks_like_result_start(lines: list[str], idx: int) -> bool:
    return idx + 1 < len(lines) and HANDLE_RE.fullmatch(lines[idx]) and DATE_RE.fullmatch(lines[idx + 1])


def parse_search_results(text: str, query_meta: dict) -> list[dict]:
    lines = clean_lines(text)
    posts = []
    i = 0
    while i < len(lines) - 2:
        if not looks_like_result_start(lines, i):
            i += 1
            continue

        handle = lines[i]
        date = lines[i + 1]
        j = i + 2
        body_lines = []
        metrics = []

        while j < len(lines):
            token = lines[j]
            if looks_like_result_start(lines, j) or is_footer_line(token):
                break
            if token == 'Translate':
                j += 1
                continue
            if NUMBER_RE.fullmatch(token):
                metrics.append(token)
                j += 1
                while j < len(lines) and NUMBER_RE.fullmatch(lines[j]):
                    metrics.append(lines[j])
                    j += 1
                break
            if SLASH_NUMBER_RE.fullmatch(token):
                j += 1
                continue
            if token.lower() == query_meta['query'].lower() and not body_lines:
                j += 1
                continue
            body_lines.append(token)
            j += 1

        post_text = ' '.join(body_lines).strip()
        if len(post_text) >= 24:
            posts.append({
                'bucket': query_meta['bucket'],
                'lang': query_meta['lang'],
                'query': query_meta['query'],
                'handle': handle,
                'date': date,
                'text': post_text,
                'metrics': metrics[:4],
                'score': engagement_score(metrics),
                'style_tags': infer_style_tags(post_text),
            })
        i = max(j, i + 1)
    return posts


def summarize_style_signals(posts: list[dict]) -> list[str]:
    if not posts:
        return [
            'гачок з першої фрази',
            'контекст захований всередині тексту, без службового вступу',
            'людський ритм, ніби це жива думка, а не контент-план',
        ]

    top = sorted(posts, key=lambda item: item.get('score', 0), reverse=True)[:12]
    short_hits = sum(1 for item in top if len(item['text']) < 120)
    question_hooks = sum(1 for item in top if '?' in item['text'])
    first_person = sum(1 for item in top if 'first_person' in item.get('style_tags', []))
    emoji_hits = sum(1 for item in top if 'emoji_punch' in item.get('style_tags', []))

    signals = [
        'контекст має бути в самому пості, без рядка "Контекст" чи пояснення згори',
        'бери ритм із топових Threads-постів: короткий гачок, одна сцена або одна думка, без води',
    ]
    if short_hits >= 4:
        signals.append('короткі та середні пости працюють краще за довгі пояснення')
    if question_hooks >= 4:
        signals.append('інколи працює прямий хук-питання, але без шаблону в кожному пості')
    if first_person >= 4:
        signals.append('першу особу використовуй як живу реакцію, а не як прес-реліз')
    if emoji_hits >= 3:
        signals.append('емодзі можна, але точково — як акцент, а не як милиця')
    signals.append('панчлайн має міняти механіку: self-own, misdirection, deadpan, faux confidence, діалог, абсурдна деталь')
    return signals[:6]


def dedupe_posts(posts: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for item in sorted(posts, key=lambda row: row.get('score', 0), reverse=True):
        key = re.sub(r'\W+', '', item['text'].lower())[:180]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def main():
    results = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'queries': SEARCH_QUERIES,
        'references': [],
        'threads_signals': [],
        'style_signals': [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for query_meta in SEARCH_QUERIES:
            url = f"https://www.threads.com/search?q={query_meta['query']}"
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=45000)
                page.wait_for_timeout(3500)
                body = page.locator('body').inner_text()
                results['references'].extend(parse_search_results(body, query_meta))
            except Exception:
                continue
        browser.close()

    deduped = dedupe_posts(results['references'])
    results['references'] = deduped[:80]
    results['threads_signals'] = [item['text'] for item in results['references'][:30]]
    results['style_signals'] = summarize_style_signals(results['references'])
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
