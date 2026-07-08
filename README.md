# yt-pod-rss

Turn a YouTube channel into a podcast RSS feed with downloadable audio files.

## How it works

1. Fetches the latest videos from a YouTube channel (skips Shorts)
2. Downloads each video's audio as an `.m4a` file into `media/`
3. Generates an RSS 2.0 feed (`feed.xml`) with `<enclosure>` elements pointing to the local audio files
4. Can run locally or via GitHub Actions (scheduled daily) and deploy to GitHub Pages

## Quick start — GitHub Actions (hosted)

This is the easiest way: fork the repo, configure it, and GitHub will regenerate and host your feed daily.

### 1. Fork

Fork this repo on GitHub.

### 2. Set your channel URL

Edit `config.yml` in your fork and change `channel_url` to your YouTube channel:

```yaml
channel_url: https://www.youtube.com/@YourChannel
```

### 3. Export YouTube cookies

Follow the [yt-dlp guide on exporting YouTube cookies](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies) to get a `cookies.txt` file.

### 4. Add cookies to your fork

You have two options:

**Option A — GitHub secret** (safer, recommended):

1. Open your fork's Settings → Secrets and variables → Actions
2. Create a new repository secret named `YT_COOKIES`
3. Paste the **entire contents** of your `cookies.txt` file as the value

**Option B — Commit cookies.txt** (simpler, private forks only):

1. Copy the exported `cookies.txt` into the repo root
2. It's already in `.gitignore` — uncomment or remove it from `.gitignore` if you want it committed

### 5. Enable GitHub Pages

1. Go to your fork's Settings → Pages
2. Under **Source**, select **GitHub Actions**
3. The feed will be available at `https://<your-username>.github.io/yt-pod-rss/feed.xml`

### 6. Run it

- The workflow runs automatically every day at 06:00 UTC
- You can also trigger it manually: Actions → Generate RSS Feed → Run workflow
- After the first run, add the RSS feed URL to your podcast app

## Running locally

```bash
# Install dependencies
pip install -r requirements.txt

# Install Deno (required by yt-dlp for JS challenge solving)
curl -fsSL https://deno.land/install.sh | sh
export PATH="$HOME/.deno/bin:$PATH"

# Generate the feed (uses channel_url from config.yml)
python generate_feed.py

# Or specify a URL directly
python generate_feed.py "https://www.youtube.com/@channel/videos"

# Test mode (uses sample data, no network calls)
python generate_feed.py --test

# Custom number of videos
python generate_feed.py -n 10
```

If you get bot-blocked, place a `cookies.txt` file in the repo root or set the `YT_COOKIES` environment variable.

## Project structure

```
yt-pod-rss/
├── config.yml                 # Channel URL and settings
├── generate_feed.py           # Main script
├── requirements.txt           # Python dependencies
├── test_data.json             # Sample data for --test mode
├── cookies.txt                # YouTube cookies (optional, not committed)
├── media/                     # Downloaded audio files (not committed)
├── feed.xml                   # Generated RSS feed (not committed)
└── .github/workflows/
    └── generate.yml           # GitHub Actions workflow (daily schedule)
```

---

Built by [@andreparames](https://github.com/andreparames) with [OpenCode](https://opencode.ai)
