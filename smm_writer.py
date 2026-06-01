import json
import os
import subprocess
from pathlib import Path

OPENCLAW = '/home/openclaw/.npm-global/bin/openclaw'
ENV_PATH = Path('/home/openclaw/.openclaw/workspace/.env.threads-content')
DEFAULT_MODEL = 'openai-codex/gpt-5.4'


def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            env[key.strip()] = value.strip()
    return env


def build_prompt(bucket: str, seed: str, fmt: str, recent_buckets: str, recent_formats: str, recent_posts: str, context_hint: str, reference_posts: str, style_signals: str, punchline_device: str) -> str:
    return f'''
Напиши ОДИН готовий пост для Threads українською мовою.

Bucket: {bucket}
Seed: {seed}
Формат: {fmt}
Недавні buckets: {recent_buckets}
Недавні formats: {recent_formats}
Контекст-підказка: {context_hint}
Референси з Threads по цій або близькій темі (не копіювати, тільки взяти ритм / тип подачі / відчуття живого поста):
{reference_posts}
Поточні стильові сигнали з Threads:
{style_signals}
Недавні готові пости, які не можна повторювати або перефразовувати занадто близько: {recent_posts}
Механіка жарту / повороту для цього поста: {punchline_device}

Вайб:
- свій в інтернеті
- живий, не канцелярський
- іронічний, але не пластиковий
- відчуття, ніби це написала реальна людина, яка реально сидить у Threads
- смішний або влучний там, де це природно
- коротший, різкіший, з нормальним інтернет-ритмом

Жорсткі правила:
- пиши як повноцінний готовий пост від першої особи або як жива пряма думка
- не пиши як рекомендацію, бриф, чернетку або пояснення до поста
- НЕ пиши окремий службовий вступ, НЕ пиши рядок "Контекст" і взагалі не винось бекграунд над постом
- якщо потрібен контекст, вмонтуй його всередину самого тексту природно, з першого або другого речення
- пост має читатися так, ніби його можна одразу публікувати
- не звучати як ШІ, маркетолог, копірайтер або контент-план
- не використовуй шаблонну кінцівку і не пояснюй жарт після жарту
- не повторюй буквально або майже буквально жоден із недавніх готових постів або референсів
- якщо bucket = gaming_news, обов'язково назви в самому пості конкретну гру / франшизу / реліз; можна взяти з context_hint або референсів
- якщо bucket = gaming_news, бажано назвати гру вже в першому реченні
- якщо bucket = twitch, обов'язково назви Twitch або явно скажи, що мова про стрім / чат / рейд
- якщо це Торонто, додай конкретний міський вайб, а не абстрактне "велике місто"
- якщо це мемний жарт, він має бути завершеним і не схожим на попередні панчлайни
- якщо формат punchline, 1-2 речення, максимум 140 символів
- якщо формат punchline, не починай пост одним і тим самим шаблоном; використай саме цю механіку: {punchline_device}
- якщо формат punchline, уникай шаблону «коли...», якщо тільки він не реально найсмішніший тут
- якщо seed несе нову тему, жарт має триматися її, а не з'їжджати в сон / to-do / соромні спогади без причини
- в іншому випадку 120-340 символів
- менше пояснень, більше ритму, конкретики, сцени, деталі або реакції
- якщо це історія, вона має звучати як реальний момент з життя, а не як літературна вправа

Поверни СУВОРО JSON без пояснень:
{{"post":"...","photo_idea":"..."}}
'''.strip()


def generate_post(bucket: str, seed: str, fmt: str, recent_buckets: str, recent_formats: str, recent_posts: str = 'none', context_hint: str = 'none', reference_posts: str = 'none', style_signals: str = 'none', punchline_device: str = 'мінідеталь з поворотом') -> dict:
    env = {**os.environ, **load_env(ENV_PATH)}
    prompt = build_prompt(
        bucket=bucket,
        seed=seed,
        fmt=fmt,
        recent_buckets=recent_buckets,
        recent_formats=recent_formats,
        recent_posts=recent_posts,
        context_hint=context_hint,
        reference_posts=reference_posts,
        style_signals=style_signals,
        punchline_device=punchline_device,
    )

    model = env.get('THREADS_WRITER_MODEL', DEFAULT_MODEL)
    thinking = env.get('THREADS_WRITER_THINKING', 'minimal')

    out = subprocess.run(
        [
            OPENCLAW,
            'agent',
            '--agent', 'smm',
            '--model', model,
            '--thinking', thinking,
            '--message', prompt,
            '--json',
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    raw = out.stdout.strip()
    payload = json.loads(raw)
    meta = payload.get('meta') or {}
    text = meta.get('finalAssistantVisibleText') or meta.get('finalAssistantRawText') or raw
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError('model did not return JSON')
    return json.loads(text[start:end + 1])
