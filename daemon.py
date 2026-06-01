import json
import subprocess
import time
from pathlib import Path

from bot import main as run_once, load_env, BASE

ENV = Path('/home/openclaw/.openclaw/workspace/.env.threads-content')
STATE = Path('/home/openclaw/.openclaw/workspace/threads_content_bot/schedule_state.json')


def toronto_day_time():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    now = _dt.datetime.now(ZoneInfo('America/Toronto'))
    return now.strftime('%Y-%m-%d'), now.hour, now.minute


def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {'last_daily_sent': None, 'last_trends_refresh': None}


def save_state(data):
    STATE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def main():
    while True:
        env = load_env(ENV)
        target_hour = int(env.get('DAILY_POST_HOUR_TORONTO', '8'))
        target_minute = int(env.get('DAILY_POST_MINUTE_TORONTO', '30'))
        state = load_state()
        state.setdefault('last_trends_refresh', None)
        day, hour, minute = toronto_day_time()

        if state.get('last_trends_refresh') != day:
            subprocess.run(['python3', str(BASE / 'trend_updater.py')], check=False)
            state['last_trends_refresh'] = day
            save_state(state)

        if (hour > target_hour or (hour == target_hour and minute >= target_minute)) and state.get('last_daily_sent') != day:
            run_once()
            state['last_daily_sent'] = day
            save_state(state)
        time.sleep(900)


if __name__ == '__main__':
    main()
