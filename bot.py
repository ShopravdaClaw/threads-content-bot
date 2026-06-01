import json
import random
import re
import subprocess
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

from smm_writer import generate_post

BASE = Path('/home/openclaw/.openclaw/workspace/threads_content_bot')
ENV = Path('/home/openclaw/.openclaw/workspace/.env.threads-content')
TOPICS = json.loads((BASE / 'topics.json').read_text())
WRITER_PROMPT = (BASE / 'writer_prompt.md').read_text()
STATE = BASE / 'state.json'
TRENDS = BASE / 'trends.json'

KNOWN_GAME_TITLES = [
    'GTA 6', 'The Witcher 4', 'CS2', 'Dota 2', 'Elden Ring', 'Death Stranding 2',
    'Silent Hill 2', 'Resident Evil 4', 'Hades II', 'Stellar Blade', 'Clair Obscur',
    'Kingdom Come', 'Marvel Rivals'
]

KNOWN_STREAM_CONTEXT = [
    'Twitch-стрім', 'рейд на Twitch', 'ігровий стрім по CS2', 'нічний Twitch-стрім',
    'стрім з чатом після катки', 'момент після рейду на Twitch'
]

PUNCHLINE_DEVICES = [
    'self-own з конкретною дрібницею',
    'deadpan контраст між пафосом і реальністю',
    'misdirection: почати серйозно, закінчити побутовою дурнею',
    'faux confidence, яка ламається в кінці',
    'діалог у 1-2 рядки',
    'абсурдна, але дуже впізнавана деталь',
]

BAD_AI_MARKERS = [
    'контекст:', 'ось пост', 'цей пост', 'цей текст', 'цей допис', 'як на мене',
    'пост для threads', 'відчуття ніби', 'у цьому пості', 'мораль історії',
    'головне нагадування', 'нагадування про те', 'і це, мабуть, головне',
]


def load_env(p):
    env = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
    return env


def load_state():
    try:
        data = json.loads(STATE.read_text())
    except Exception:
        data = {'seen': []}
    data.setdefault('seen', [])
    data.setdefault('recent_buckets', [])
    data.setdefault('recent_formats', [])
    data.setdefault('recent_posts', [])
    data.setdefault('recent_punchline_devices', [])
    return data


def save_state(data):
    STATE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def tg_api(method, payload, token):
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(f'https://api.telegram.org/bot{token}/{method}', data=data, method='POST')
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def normalize_text(text):
    text = text.lower().replace('’', "'").replace('`', "'")
    text = re.sub(r'[^\w\s\'ʼ]+', ' ', text, flags=re.UNICODE)
    text = re.sub(r'\s+', ' ', text, flags=re.UNICODE).strip()
    return text


def recent_posts_for_prompt(state, limit=6):
    items = state.get('recent_posts', [])[-limit:]
    posts = []
    for item in items:
        if isinstance(item, dict):
            text = (item.get('post') or '').strip()
        else:
            text = str(item).strip()
        if text:
            posts.append(text)
    return ' | '.join(posts) if posts else 'none'


def is_too_similar(candidate, state, threshold=0.84, token_overlap_threshold=0.7):
    norm_candidate = normalize_text(candidate)
    if not norm_candidate:
        return False
    candidate_tokens = set(norm_candidate.split())
    for item in state.get('recent_posts', [])[-12:]:
        previous = item.get('post', '') if isinstance(item, dict) else str(item)
        norm_previous = normalize_text(previous)
        if not norm_previous:
            continue
        if norm_candidate == norm_previous:
            return True
        if SequenceMatcher(None, norm_candidate, norm_previous).ratio() >= threshold:
            return True
        previous_tokens = set(norm_previous.split())
        if candidate_tokens and previous_tokens:
            overlap = len(candidate_tokens & previous_tokens) / max(1, len(candidate_tokens | previous_tokens))
            if overlap >= token_overlap_threshold:
                return True
    return False


def evaluate_post(post, bucket, fmt, seed, spec, state):
    text = (post or '').strip()
    score = 100
    reasons = []
    low = text.lower()
    norm = normalize_text(text)

    if not text:
        return 0, ['empty']

    if any(marker in low for marker in BAD_AI_MARKERS):
        score -= 35
        reasons.append('ai_marker')

    if 'контекст:' in low:
        score -= 50
        reasons.append('context_label')

    if fmt == 'punchline':
        if len(text) > 140:
            score -= 35
            reasons.append('too_long_for_punchline')
        if low.startswith('коли '):
            score -= 12
            reasons.append('template_when')
    else:
        if len(text) < 110:
            score -= 18
            reasons.append('too_short')
        if len(text) > 360:
            score -= 18
            reasons.append('too_long')

    if is_too_similar(text, state):
        score -= 45
        reasons.append('too_similar_recent')

    seed_tokens = [tok for tok in normalize_text(seed).split() if len(tok) > 3]
    overlap = sum(1 for tok in seed_tokens if tok in norm)
    if seed_tokens and overlap == 0 and bucket != 'meme_joke':
        score -= 15
        reasons.append('weak_topic_overlap')

    if bucket == 'gaming_news' and not any(title.lower() in low for title in KNOWN_GAME_TITLES):
        score -= 20
        reasons.append('missing_game_title')

    if bucket == 'twitch' and not any(token in low for token in ['twitch', 'стрім', 'чат', 'рейд']):
        score -= 20
        reasons.append('missing_stream_context')

    ref_blob = (spec.get('reference_posts') or '').lower()
    if ref_blob != 'none' and len(text) > 0:
        ref_hits = 0
        for chunk in ref_blob.split('|'):
            words = [tok for tok in normalize_text(chunk).split() if len(tok) > 4]
            if words and any(word in norm for word in words[:6]):
                ref_hits += 1
        if ref_hits >= 2:
            score -= 12
            reasons.append('too_close_to_references')

    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    if len(sentences) >= 3 and len(set(sentences)) < len(sentences):
        score -= 10
        reasons.append('repetitive_rhythm')

    return max(score, 0), reasons


NON_PUNCHLINE_FORMATS = ['mini_story', 'observation', 'one_liner', 'dialogue', 'chaotic_bit']

REQUIRED_SLOTS = [
    {'label': 'Гра 1', 'bucket': 'gaming_news', 'allowed_formats': NON_PUNCHLINE_FORMATS},
    {'label': 'Гра 2', 'bucket': 'gaming_news', 'allowed_formats': NON_PUNCHLINE_FORMATS},
    {'label': 'Twitch / стрімінг', 'bucket': 'twitch', 'allowed_formats': NON_PUNCHLINE_FORMATS},
    {'label': 'Жиза', 'bucket': 'zhiza', 'allowed_formats': NON_PUNCHLINE_FORMATS},
    {'label': 'Ностальгія', 'bucket': 'nostalgia_2000s', 'format': 'nostalgia_mono'},
    {'label': 'Панчлайн', 'bucket': 'meme_joke', 'format': 'punchline'},
]


def build_pool(bucket, state, avoid_recent=4):
    recent = state.get('recent_buckets', [])[-avoid_recent:]
    seen = set(state.get('seen', []))
    rows = []
    for item in TOPICS.get(bucket, []):
        key = f'{bucket}:{item}'
        penalty = 100 if bucket in recent else 0
        if key in seen:
            penalty += 1000
        rows.append((penalty + random.randint(0, 20), bucket, item, key))
    rows.sort(key=lambda x: x[0])
    return rows


def pick_topics(state):
    chosen = []
    chosen_keys = set()

    for slot in REQUIRED_SLOTS:
        bucket = slot['bucket']
        pool = build_pool(bucket, state)
        selected = None
        for _, row_bucket, item, key in pool:
            if key in chosen_keys:
                continue
            selected = (slot, row_bucket, item, key)
            break
        if not selected:
            for item in TOPICS.get(bucket, []):
                key = f'{bucket}:{item}'
                if key in chosen_keys:
                    continue
                selected = (slot, bucket, item, key)
                break
        if not selected:
            continue
        chosen.append(selected)
        chosen_keys.add(selected[3])

    return chosen


FORMATS = ['mini_story', 'observation', 'one_liner', 'dialogue', 'nostalgia_mono', 'chaotic_bit', 'punchline']


def load_trends():
    try:
        return json.loads(TRENDS.read_text())
    except Exception:
        return {}


def extract_known_titles(text):
    found = []
    lowered = text.lower()
    for title in KNOWN_GAME_TITLES:
        if title.lower() in lowered:
            found.append(title)
    return found


def bucket_aliases(bucket):
    aliases = {
        'gaming_news': {'gaming_news', 'games', 'gaming'},
        'twitch': {'twitch', 'streaming'},
        'zhiza': {'zhiza', 'life', 'adulting'},
        'nostalgia_2000s': {'nostalgia_2000s', 'nostalgia'},
        'toronto_life': {'toronto_life', 'toronto'},
        'meme_joke': {'meme_joke', 'zhiza'},
    }
    return aliases.get(bucket, {bucket})


def build_context_hint(bucket, seed, trends=None):
    trends = trends or {}
    signals = trends.get('threads_signals', [])
    references = trends.get('references', [])
    seed_titles = extract_known_titles(seed)
    signal_titles = []
    for signal in signals:
        signal_titles.extend(extract_known_titles(signal))
    ref_titles = []
    for ref in references:
        if ref.get('bucket') in bucket_aliases(bucket):
            ref_titles.extend(extract_known_titles(ref.get('text', '')))
    unique_titles = []
    for title in seed_titles + signal_titles + ref_titles:
        if title not in unique_titles:
            unique_titles.append(title)

    if bucket == 'gaming_news':
        if unique_titles:
            return f"ігровий контекст: {unique_titles[0]}"
        if any(x in seed.lower() for x in ['ще не вийшла', 'анонс', 'трейлер', 'реліз']):
            return 'ігровий контекст: гучний анонс на рівні GTA 6 / CS2 / The Witcher 4'
        return 'ігровий контекст: велика впізнавана гра, яку реально обговорюють у Threads'

    if bucket == 'twitch':
        if 'рейд' in seed.lower():
            return 'стрімінг контекст: Twitch-рейд після ігрового стріму'
        if 'чат' in seed.lower():
            return 'стрімінг контекст: Twitch-стрім з активним чатом'
        return random.choice(KNOWN_STREAM_CONTEXT)

    if bucket == 'nostalgia_2000s':
        return 'контекст: нульові, аська, mp3, блютуз, MTV, кнопкові телефони'

    if bucket == 'zhiza':
        return 'контекст: проста життєва сцена без філософської надбудови'

    if bucket == 'meme_joke':
        return 'контекст: короткий завершений рофл на конкретну тему'

    return seed


def find_reference_posts(bucket, seed, trends=None, limit=3):
    trends = trends or {}
    references = trends.get('references', [])
    aliases = bucket_aliases(bucket)
    seed_words = set(normalize_text(seed).split())
    scored = []
    for ref in references:
        ref_bucket = ref.get('bucket') or ''
        if ref_bucket not in aliases and bucket != 'meme_joke':
            continue
        text = (ref.get('text') or '').strip()
        if len(text) < 20:
            continue
        ref_words = set(normalize_text(text).split())
        overlap = len(seed_words & ref_words)
        score = ref.get('score', 0) + overlap * 500
        scored.append((score, text, ref))

    if bucket == 'meme_joke' and not scored:
        for ref in references:
            text = (ref.get('text') or '').strip()
            if 20 <= len(text) <= 180:
                scored.append((ref.get('score', 0), text, ref))

    chosen = []
    seen = set()
    for _, text, ref in sorted(scored, key=lambda row: row[0], reverse=True):
        key = normalize_text(text)
        if key in seen:
            continue
        seen.add(key)
        chosen.append(f"@{ref.get('handle', 'author')}: {text}")
        if len(chosen) >= limit:
            break
    return ' | '.join(chosen) if chosen else 'none'


def build_writer_spec(bucket, seed, fmt, state):
    recent_formats = ', '.join(state.get('recent_formats', [])[-4:]) or 'none'
    recent_buckets = ', '.join(state.get('recent_buckets', [])[-4:]) or 'none'
    recent_posts = recent_posts_for_prompt(state)
    trends = load_trends()
    context_hint = build_context_hint(bucket, seed, trends)
    reference_posts = find_reference_posts(bucket, seed, trends)
    style_signals = ' | '.join(trends.get('style_signals', [])[:6]) or 'none'
    recent_devices = state.get('recent_punchline_devices', [])[-3:]
    punchline_pool = [item for item in PUNCHLINE_DEVICES if item not in recent_devices] or list(PUNCHLINE_DEVICES)
    punchline_device = random.choice(punchline_pool)
    return {
        'bucket': bucket,
        'seed': seed,
        'format': fmt,
        'recent_formats': recent_formats,
        'recent_buckets': recent_buckets,
        'recent_posts': recent_posts,
        'context_hint': context_hint,
        'reference_posts': reference_posts,
        'style_signals': style_signals,
        'writer_prompt': WRITER_PROMPT,
        'target_model': 'openai-codex/gpt-5.4',
        'punchline_device': punchline_device,
    }


def pick_format(state, bucket, forced_format=None, allowed_formats=None):
    if forced_format:
        return forced_format
    base_pool = allowed_formats or [f for f in FORMATS if f != 'punchline']
    recent = state.get('recent_formats', [])[-4:]
    pool = [f for f in base_pool if f not in recent]
    if not pool:
        pool = list(base_pool)
    if bucket == 'funny_story' and 'mini_story' in pool:
        return 'mini_story'
    return random.choice(pool)


def make_post(bucket, seed, fmt, state):
    spec = build_writer_spec(bucket, seed, fmt, state)
    attempts = 5 if fmt == 'punchline' else 4
    last_generated = None
    best_candidate = None
    best_score = -1
    for _ in range(attempts):
        generated = generate_post(
            bucket=bucket,
            seed=seed,
            fmt=fmt,
            recent_buckets=spec['recent_buckets'],
            recent_formats=spec['recent_formats'],
            recent_posts=spec['recent_posts'],
            context_hint=spec['context_hint'],
            reference_posts=spec['reference_posts'],
            style_signals=spec['style_signals'],
            punchline_device=spec['punchline_device'],
        )
        last_generated = generated
        score, reasons = evaluate_post(generated.get('post', ''), bucket, fmt, seed, spec, state)
        generated['quality_score'] = score
        generated['quality_reasons'] = reasons
        if score > best_score:
            best_candidate = generated
            best_score = score
        if score >= 74 and not is_too_similar(generated.get('post', ''), state):
            generated['writer_spec'] = spec
            return generated
    chosen = best_candidate or last_generated or {'post': '', 'photo_idea': ''}
    chosen['writer_spec'] = spec
    return chosen


def main():
    subprocess.run(['python3', str(BASE / 'trend_updater.py')], check=False)
    global TOPICS
    TOPICS = json.loads((BASE / 'topics.json').read_text())
    env = load_env(ENV)
    state = load_state()
    options = pick_topics(state)
    if len(options) < len(REQUIRED_SLOTS):
        state['seen'] = []
        state['recent_buckets'] = []
        options = pick_topics(state)
    blocks = []
    for i, (slot, bucket, seed, key) in enumerate(options, start=1):
        fmt = pick_format(state, bucket, slot.get('format'), slot.get('allowed_formats'))
        made = make_post(bucket, seed, fmt, state)
        label = slot['label']
        ref = made.get('writer_spec', {}).get('reference_posts', 'none')
        quality = made.get('quality_score')
        block = [f"<b>{i}. {label}</b>", made['post'], f"Фото: {made['photo_idea']}"]
        if quality is not None:
            block.append(f"Оцінка: {quality}/100")
        if ref != 'none':
            block.append(f"Референси: {ref}")
        blocks.append('\n\n'.join(block))
        state['seen'].append(key)
        state.setdefault('recent_buckets', []).append(bucket)
        state.setdefault('recent_formats', []).append(fmt)
        if fmt == 'punchline':
            state.setdefault('recent_punchline_devices', []).append(made.get('writer_spec', {}).get('punchline_device'))
        state.setdefault('recent_posts', []).append({
            'bucket': bucket,
            'format': fmt,
            'seed': seed,
            'post': made.get('post', '').strip(),
        })
    state['recent_buckets'] = state.get('recent_buckets', [])[-40:]
    state['recent_formats'] = state.get('recent_formats', [])[-40:]
    state['recent_posts'] = state.get('recent_posts', [])[-30:]
    state['recent_punchline_devices'] = state.get('recent_punchline_devices', [])[-12:]
    text = "🧵 Нові пости для Threads\n\n" + "\n\n— — —\n\n".join(blocks)
    tg_api('sendMessage', {
        'chat_id': env['TELEGRAM_CHAT_ID'],
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': 'true'
    }, env['BOT_TOKEN'])
    save_state(state)


if __name__ == '__main__':
    main()
