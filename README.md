# Halo News AI Bot Pro

A free-friendly Halo news system for Telegram:

- finds Halo news from trusted sources;
- classifies items by type and importance;
- generates an English Telegram post;
- sends a Russian admin version;
- supports automatic posting, review queue, or hybrid mode;
- includes a visual Streamlit admin panel with an editable EN/RU post editor;
- runs on GitHub Actions, so your PC does not need to stay online 24/7.

Default mode is **free**: `AI_PROVIDER=template`. Optional AI providers can be added later, but the project works without paid AI.

---

## What is inside

```text
src/halo_news_bot/
  sources.py          # Halo Waypoint, Xbox Wire RSS, Steam Halo Infinite news
  classifier.py       # news type + importance score + autopost decision
  generator.py        # template posts; optional OpenAI/Hugging Face providers
  storage.py          # JSON queue/state storage for GitHub Actions
  telegram_client.py  # sendMessage/sendPhoto + inline source button
  runner.py           # fetch, queue, publish pipeline
  cli.py              # halo-news-bot command

admin/app.py          # visual Streamlit editor
.github/workflows/    # scheduled GitHub Actions runner
data/                 # queue/state files committed by the workflow
tests/                # basic tests
```

---

## Modes

```env
POST_MODE=queue
```

Everything goes to the editor first. Safest mode.

```env
POST_MODE=hybrid
```

Official high-score news can autopost. Everything else waits in the editor.

```env
POST_MODE=auto
```

Posts every eligible item that passes autopost rules. Use carefully.

---

## Free setup with GitHub Actions

### 1. Create a Telegram bot

Use BotFather, create a bot, and copy the token.

### 2. Add the bot to your channel

Add the bot to `@Halo_Combat_Evolved` as an admin with permission to post messages.

### 3. Get your admin chat ID

Send any message to your bot, then open:

```text
https://api.telegram.org/botYOUR_TOKEN/getUpdates
```

Find your numeric `chat.id`.

### 4. Push this project to GitHub

Create a GitHub repository and upload these files.

### 5. Add GitHub repository secrets

Repository → Settings → Secrets and variables → Actions → Secrets:

```text
TELEGRAM_BOT_TOKEN = your Telegram bot token
ADMIN_CHAT_ID = your numeric Telegram user ID
```

Optional, only if you later want paid/optional AI:

```text
OPENAI_API_KEY = your key
HF_API_TOKEN = your Hugging Face token
```

### 6. Add GitHub variables

Repository → Settings → Secrets and variables → Actions → Variables:

```text
TELEGRAM_CHANNEL_ID=@Halo_Combat_Evolved
DRY_RUN=true
POST_MODE=queue
AI_PROVIDER=template
AUTO_POST_MIN_SCORE=82
MAX_POSTS_PER_DAY=5
```

Keep `DRY_RUN=true` for the first test.

### 7. Run manually once

GitHub → Actions → Halo News Bot → Run workflow.

After you confirm queue/state updates are working, set:

```text
DRY_RUN=false
```

---

## Visual admin panel

The admin panel is in:

```text
admin/app.py
```

Run locally:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[admin]
streamlit run admin/app.py
```

### Streamlit Cloud deployment

For a free web editor, deploy the GitHub repository to Streamlit Community Cloud.

Add these Streamlit secrets:

```toml
ADMIN_PANEL_PASSWORD="choose-a-strong-password"
TELEGRAM_BOT_TOKEN="123456:your-bot-token"
TELEGRAM_CHANNEL_ID="@Halo_Combat_Evolved"
ADMIN_CHAT_ID="123456789"
GITHUB_TOKEN="github_pat_..."
GITHUB_REPO="your-github-username/your-repo-name"
GITHUB_BRANCH="main"
DRY_RUN="false"
```

Why `GITHUB_TOKEN` is needed: the visual editor reads and writes `data/queue.json` directly in your GitHub repo. This lets GitHub Actions and Streamlit share the same free queue without a paid database.

For the token, create a fine-grained GitHub token with access only to this repository and Contents read/write permission.

---

## Recommended settings for your channel

Start safe:

```env
POST_MODE=queue
DRY_RUN=false
AI_PROVIDER=template
MAX_POSTS_PER_DAY=5
```

After a few days:

```env
POST_MODE=hybrid
AUTO_POST_MIN_SCORE=88
MAX_POSTS_PER_DAY=4
```

This means:

- official major news can autopost;
- weaker news waits in the editor;
- rumors do not autopost;
- RU admin version is still sent to you.

---

## Add more sources

Default:

```env
ENABLED_SOURCES=halo_waypoint,xbox_wire,steam_halo_infinite
```

You can add custom RSS feeds:

```env
ENABLED_SOURCES=halo_waypoint,xbox_wire,steam_halo_infinite,custom_rss
CUSTOM_RSS_URLS=https://example.com/feed.xml,https://another-site.com/rss
```

Custom RSS feeds are treated as non-official, so they usually go to the editor instead of autoposting.

---

## Optional AI

Free default:

```env
AI_PROVIDER=template
```

Optional OpenAI:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
```

Optional Hugging Face experimental provider:

```env
AI_PROVIDER=huggingface
HF_API_TOKEN=...
```

If an optional AI provider fails, the bot automatically falls back to template generation.

---

## Local commands

```bash
halo-news-bot fetch      # fetch and add items to queue
halo-news-bot publish    # publish eligible queued items
halo-news-bot run        # fetch + publish according to POST_MODE
halo-news-bot status     # show state and queue counts
```

---

## Quality controls

The bot includes:

- source whitelist;
- duplicate protection by URL and normalized title;
- importance score;
- news type detection;
- rumor penalty;
- blacklist words;
- daily post limits;
- per-run post limits;
- queue editor;
- dry-run mode;
- RU admin summary explaining why the bot selected the item.

---

## Suggested workflow

```text
GitHub Actions checks news every 45 minutes
↓
New Halo items are saved to data/queue.json
↓
Open Streamlit admin panel
↓
Edit EN/RU text
↓
Publish EN to @Halo_Combat_Evolved
↓
Send RU version to admin
```

This gives you automation without losing editorial control.
