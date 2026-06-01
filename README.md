# Threads Content Bot

Generates several ready-to-post Threads options in Ukrainian using live Threads references, trend scraping, and style constraints aimed at human-sounding output.

## What it does
- scrapes Threads search results in Ukrainian and English
- extracts reference posts and style signals
- generates post options with embedded context
- rotates punchline mechanisms to reduce repetition
- sends post options to Telegram

## Setup
1. Create `.env.threads-content` from `.env.threads-content.example`.
2. Install dependencies:
   ```bash
   python3 -m pip install playwright
   python3 -m playwright install chromium
   ```
3. Run once:
   ```bash
   python3 bot.py
   ```
4. Run daemon:
   ```bash
   python3 daemon.py
   ```
