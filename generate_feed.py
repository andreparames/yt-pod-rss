#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"

ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
ET.register_namespace("itunes", ITUNES_NS)

NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def itunes(tag):
    return f"{{{ITUNES_NS}}}{tag}"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate an RSS 2.0 podcast feed from a YouTube channel.")
    parser.add_argument("url", nargs="?", help="YouTube channel URL")
    parser.add_argument("-o", "--output", default=None, help="Output RSS file (default: {name}.xml)")
    parser.add_argument("-n", "--num-videos", type=int, default=20, help="Number of recent videos (default: 20)")
    parser.add_argument("-c", "--config", default="config.yml", help="Config file (default: config.yml)")
    parser.add_argument("--test", action="store_true", help="Use sample test data instead of YouTube")
    return parser.parse_args()


def load_config(path):
    if not os.path.exists(path):
        return None
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        print("Install pyyaml: pip install pyyaml", file=sys.stderr)
        sys.exit(1)


def validate_name(name):
    if not NAME_RE.match(name):
        print(f"Invalid feed name: {name!r}. Use only letters, digits, hyphens, underscores.", file=sys.stderr)
        sys.exit(1)


def _is_short(entry):
    title = (entry.get("title") or "").lower()
    if "#shorts" in title:
        return True
    duration = entry.get("duration")
    if duration is not None and duration <= 60:
        return True
    return False


def resolve_cookies():
    cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
    if os.path.exists(cookies_path):
        return cookies_path
    env_cookies = os.environ.get("YT_COOKIES")
    if env_cookies:
        tmp = os.path.join(os.path.dirname(__file__), ".cookies_tmp.txt")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(env_cookies)
        return tmp
    return None


def base_opts(player_client=None):
    opts = {"quiet": True, "remote_components": ["ejs:github"]}
    if player_client:
        opts["extractor_args"] = {"youtube": {"player_client": [player_client]}}
    cookie_file = resolve_cookies()
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts


def download_audio(video_id, media_dir, feed_name, player_client=None):
    import yt_dlp

    download_opts = {
        **base_opts(player_client),
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": os.path.join(media_dir, "%(id)s.%(ext)s"),
        "nooverwrites": True,
    }
    with yt_dlp.YoutubeDL(download_opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)

    ext = info.get("ext", "m4a")
    filepath = os.path.join(media_dir, f"{video_id}.{ext}")
    if not os.path.exists(filepath):
        from glob import glob
        matches = glob(os.path.join(media_dir, f"{video_id}.*"))
        filepath = matches[0] if matches else filepath

    size = os.path.getsize(filepath)
    mime = "audio/mp4" if ext == "m4a" else f"audio/{ext}"
    rel_path = f"media/{feed_name}/{video_id}.{ext}"
    return info, rel_path, mime, size


def process_channel(name, channel_url, num_videos, player_client=None):
    import yt_dlp

    channel_url = channel_url.rstrip("/")
    if not channel_url.endswith("/videos"):
        channel_url += "/videos"

    with yt_dlp.YoutubeDL({**base_opts(player_client), "extract_flat": "in_playlist"}) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    channel_title = info.get("channel", info.get("title", ""))
    entries = info.get("entries", [])
    if not entries:
        print(f"  No videos found for {name}.", file=sys.stderr)
        return []

    media_dir = os.path.join(os.path.dirname(__file__), "media", name)
    os.makedirs(media_dir, exist_ok=True)

    videos = []
    candidates = 0
    for entry in entries:
        if len(videos) >= num_videos:
            break
        if _is_short(entry):
            continue

        candidates += 1
        vid = entry["id"]
        print(f"  Downloading {vid}...", file=sys.stderr)
        try:
            vinfo, rel_path, mime, size = download_audio(vid, media_dir, name, player_client)
        except Exception as e:
            print(f"  Error downloading {vid}: {e}", file=sys.stderr)
            continue

        videos.append({
            "title": vinfo.get("title", entry.get("title", "")),
            "description": vinfo.get("description") or entry.get("description", ""),
            "published": vinfo.get("upload_date") or entry.get("upload_date", ""),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "video_id": vid,
            "audio_url": rel_path,
            "audio_type": mime,
            "length": size,
            "channel_title": channel_title,
        })

    if candidates and not videos:
        raise RuntimeError(f"Could not download any videos for {name}")

    return videos


def load_test_data():
    test_data_path = os.path.join(os.path.dirname(__file__), "test_data.json")
    if not os.path.exists(test_data_path):
        return None
    with open(test_data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_sample_videos(feed_name="sample"):
    return [
        {
            "title": "Understanding Quantum Computing",
            "description": "A deep dive into the world of quantum computing.",
            "published": "20260315",
            "url": "https://www.youtube.com/watch?v=sample1",
            "video_id": "sample1",
            "audio_url": f"media/{feed_name}/sample1.mp3",
            "audio_type": "audio/mpeg",
            "length": 12345678,
            "channel_title": "Sample Channel",
        },
        {
            "title": "Python 3.14 New Features Explained",
            "description": "Exploring the latest features in Python 3.14.",
            "published": "20260310",
            "url": "https://www.youtube.com/watch?v=sample2",
            "video_id": "sample2",
            "audio_url": f"media/{feed_name}/sample2.mp3",
            "audio_type": "audio/mpeg",
            "length": 23456789,
            "channel_title": "Sample Channel",
        },
        {
            "title": "Building CLI Tools in Rust",
            "description": "Step-by-step guide to building CLI tools using Rust.",
            "published": "20260305",
            "url": "https://www.youtube.com/watch?v=sample3",
            "video_id": "sample3",
            "audio_url": f"media/{feed_name}/sample3.mp3",
            "audio_type": "audio/mpeg",
            "length": 34567890,
            "channel_title": "Sample Channel",
        },
        {
            "title": "The Future of AI Assistants",
            "description": "A discussion about AI-powered assistants.",
            "published": "20260228",
            "url": "https://www.youtube.com/watch?v=sample4",
            "video_id": "sample4",
            "audio_url": f"media/{feed_name}/sample4.mp3",
            "audio_type": "audio/mpeg",
            "length": 45678901,
            "channel_title": "Sample Channel",
        },
        {
            "title": "Docker for Beginners",
            "description": "Everything you need to get started with Docker.",
            "published": "20260220",
            "url": "https://www.youtube.com/watch?v=sample5",
            "video_id": "sample5",
            "audio_url": f"media/{feed_name}/sample5.mp3",
            "audio_type": "audio/mpeg",
            "length": 56789012,
            "channel_title": "Sample Channel",
        },
    ]


def parse_pub_date(published):
    if not published:
        return ""
    if isinstance(published, str) and len(published) == 8:
        dt = datetime(int(published[:4]), int(published[4:6]), int(published[6:8]), tzinfo=timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    if isinstance(published, (int, float)):
        dt = datetime.fromtimestamp(published, tz=timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    return str(published)


def resolve_url(path_or_url, site_url):
    if not path_or_url:
        return ""
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    if site_url:
        return f"{site_url}/{path_or_url.lstrip('/')}"
    return path_or_url


def generate_rss(videos, channel_url, name, meta=None):
    meta = meta or {}
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    site_url = os.environ.get("SITE_URL", "").rstrip("/")

    channel_title = meta.get("title") or (videos[0]["channel_title"] if videos else name)
    description = meta.get("description") or f"Podcast feed for {channel_title}"
    language = meta.get("language") or "en-us"
    author = meta.get("author") or channel_title
    owner_name = meta.get("owner_name") or author
    owner_email = meta.get("owner_email") or ""
    artwork_url = resolve_url(meta.get("artwork"), site_url)
    feed_url = resolve_url(f"{name}.xml", site_url)

    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = meta.get("link") or channel_url

    atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
    atom_link.set("href", feed_url)
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    ET.SubElement(channel, "language").text = language
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    ET.SubElement(channel, "description").text = description

    ET.SubElement(channel, itunes("author")).text = author
    if owner_email:
        owner = ET.SubElement(channel, itunes("owner"))
        ET.SubElement(owner, itunes("name")).text = owner_name
        ET.SubElement(owner, itunes("email")).text = owner_email

    if artwork_url:
        ET.SubElement(channel, itunes("image"), href=artwork_url)

    category = meta.get("category")
    if category:
        cat = ET.SubElement(channel, itunes("category"), text=category)
        if meta.get("subcategory"):
            ET.SubElement(cat, itunes("category"), text=meta["subcategory"])

    ET.SubElement(channel, itunes("explicit")).text = "true" if meta.get("explicit") else "false"
    ET.SubElement(channel, itunes("type")).text = meta.get("type") or "episodic"

    image = ET.SubElement(channel, "image")
    ET.SubElement(image, "url").text = artwork_url or "https://www.google.com/s2/favicons?domain=youtube.com&sz=128"
    ET.SubElement(image, "title").text = channel_title
    ET.SubElement(image, "link").text = meta.get("link") or channel_url

    for v in videos:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = v["title"]
        ET.SubElement(item, "link").text = v["url"]
        ET.SubElement(item, "guid", isPermaLink="true").text = v["url"]

        pub_date = parse_pub_date(v.get("published"))
        if pub_date:
            ET.SubElement(item, "pubDate").text = pub_date

        if v.get("description"):
            ET.SubElement(item, "description").text = v["description"]

        ET.SubElement(item, itunes("explicit")).text = "true" if meta.get("explicit") else "false"

        if v.get("audio_url"):
            enc = ET.SubElement(item, "enclosure")
            audio_url = v["audio_url"]
            if site_url:
                audio_url = f"{site_url}/{audio_url.lstrip('/')}"
            enc.set("url", audio_url)
            enc.set("type", v.get("audio_type", "audio/mpeg"))
            enc.set("length", str(v.get("length", "0")))

    raw = ET.tostring(rss, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + raw


def write_feed(videos, channel_url, name, output_path, meta=None):
    rss_xml = generate_rss(videos, channel_url, name, meta)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rss_xml)
    print(f"  Written {output_path} with {len(videos)} items.", file=sys.stderr)


def main():
    args = parse_args()

    if args.test:
        feed_name = args.url or "test"
        videos = generate_sample_videos(feed_name)
        output = args.output or f"{feed_name}.xml"
        channel_url = "https://youtube.com/@test"
        write_feed(videos, channel_url, feed_name, output)
        return

    if args.url:
        feed_name = "feed"
        output = args.output or f"{feed_name}.xml"
        validate_name(feed_name)
        client = None
        videos = process_channel(feed_name, args.url, args.num_videos, client)
        write_feed(videos, args.url, feed_name, output, meta={})
        return

    config = load_config(args.config)
    if not config:
        print(f"No config file found at {args.config}", file=sys.stderr)
        sys.exit(1)

    feeds = config.get("feeds", [])
    if not feeds:
        print("No feeds defined in config.yml", file=sys.stderr)
        sys.exit(1)

    for feed in feeds:
        name = feed.get("name", "").strip()
        url = feed.get("channel_url", "").strip()
        if not name or not url:
            print("Skipping feed with missing name or channel_url", file=sys.stderr)
            continue
        validate_name(name)
        client = feed.get("player_client") or None
        num = feed.get("num_videos") or args.num_videos
        output = args.output or f"{name}.xml"
        print(f"Processing feed: {name}", file=sys.stderr)
        videos = process_channel(name, url, num, player_client=client)
        write_feed(videos, url, name, output, meta=feed)


if __name__ == "__main__":
    main()
