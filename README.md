# Threads Content Bot

A Telegram-assisted content bot that scans Threads, collects live reference posts, and drafts Ukrainian post options that sound more human and less templated.

## Features
- searches Threads in Ukrainian and English
- extracts reference posts and style signals from live search results
- generates several post options with context embedded inside the post
- rotates joke mechanics to avoid repeating the same punchline pattern
- scores drafts before sending them to Telegram

## Stack
- Python 3
- Playwright
- OpenClaw agent runner
- Telegram Bot API

## Setup
1. Copy `.env.threads-content.example` to `.env.threads-content` and fill in your values.
2. Install dependencies:
   ```bash
   python3 -m pip install playwright
   python3 -m playwright install chromium
   ```
3. Run once:
   ```bash
   python3 bot.py
   ```
4. Run the scheduler:
   ```bash
   python3 daemon.py
   ```

## Notes
- Secrets are not included in this repository.
- Generated trend/state files are local runtime artifacts and should stay out of git.
