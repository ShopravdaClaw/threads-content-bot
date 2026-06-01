import json
import subprocess
from pathlib import Path

BASE = Path('/home/openclaw/.openclaw/workspace/threads_content_bot')
TOPICS = BASE / 'topics.json'
TRENDS = BASE / 'trends.json'

DEFAULT_TRENDS = {
    'threads_signals': [
        'жиза про вигорання від інтернету',
        'ностальгія за нульовими',
        'іронія про доросле життя',
        'стрімерський побут',
        'мікроісторії про Торонто',
        'іронічні реакції на ігрові новини'
    ],
    'style_signals': [
        'контекст усередині поста',
        'короткий людський ритм',
        'міняй механіку жарту',
        'менше пояснень після панчлайну'
    ],
    'references': []
}

MAX_TOPIC_ITEMS = 24


def load_json(path, fallback):
    try:
        return json.loads(path.read_text())
    except Exception:
        return fallback


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def normalize(text: str) -> str:
    return ' '.join(text.lower().split())


def append_topic(topics: dict, bucket: str, text: str):
    text = text.strip()
    if len(text) < 18:
        return
    topics.setdefault(bucket, [])
    normalized = normalize(text)
    existing = {normalize(item) for item in topics[bucket]}
    if normalized in existing:
        return
    topics[bucket].insert(0, text)
    topics[bucket] = topics[bucket][:MAX_TOPIC_ITEMS]


BUCKET_HINTS = {
    'twitch': ['стрім', 'twitch', 'stream', 'chat', 'рейд'],
    'nostalgia_2000s': ['носталь', '2000', 'дитинств', 'old', 'remember'],
    'zhiza': ['жиза', 'adulting', 'too real', 'life', 'mood'],
    'gaming_news': ['гру', 'ігр', 'gaming', 'gta', 'cs2'],
    'toronto_life': ['торонто', 'toronto'],
}


def bucket_for_reference(item: dict) -> str | None:
    bucket = item.get('bucket')
    if bucket:
        return bucket
    text = normalize(item.get('text', ''))
    for name, markers in BUCKET_HINTS.items():
        if any(marker in text for marker in markers):
            return name
    return None


def main():
    subprocess.run(['python3', str(BASE / 'threads_trend_scraper.py')], check=False)
    topics = load_json(TOPICS, {})
    trends = load_json(TRENDS, DEFAULT_TRENDS)

    for ref in trends.get('references', []):
        bucket = bucket_for_reference(ref)
        if not bucket:
            continue
        append_topic(topics, bucket, ref.get('text', ''))

    save_json(TOPICS, topics)
    save_json(TRENDS, trends)


if __name__ == '__main__':
    main()
