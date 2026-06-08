name: Halo News Bot

on:
  schedule:
    - cron: "*/30 * * * *"
  workflow_dispatch:

jobs:
  run-bot:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo
        uses: actions/checkout@v5  # обновлено с v4

      - name: Set up Python
        uses: actions/setup-python@v6  # обновлено с v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e .

      - name: Run Halo Bot
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHANNEL_ID: ${{ secrets.TELEGRAM_CHANNEL_ID }}
          ADMIN_CHAT_ID: ${{ secrets.ADMIN_CHAT_ID }}
          AI_PROVIDER: template
          POST_MODE: hybrid
          DRY_RUN: true
          MAX_POSTS_PER_DAY: 5
        run: |
          halo-news-bot --once
