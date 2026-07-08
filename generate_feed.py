#!/usr/bin/env python3
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ET.register_namespace("atom", "http://www.w3.org/2005/Atom")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate an RSS 2.0 podcast feed from a YouTube channel.")
    parser.add_argument("url", nargs="?", help="YouTube channel URL (overrides config.yml)")
    parser.add_argument("-o", "--output", default="feed.xml", help="Output RSS file (default: feed.xml)")
    parser.add_argument("-n", "--num-videos", type=int, default=20, help="Number of recent videos (default: 20)")
    parser.add_argument("-c", "--config", default="config.yml", help="Config file (default: config.yml)")
    parser.add_argument("--test", action="store_true", help="Use sample test data instead of YouTube")
    return parser.parse_args()


def load_config(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    config = {}
    for line in text.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, val = line.partition(":")
            config[key.strip()] = val.strip().strip("\"'")
    return config


def _is_short(entry):
    title = (entry.get("title") or "").lower()
    if "#shorts" in title:
        return True
    duration = entry.get("duration")
    if duration is not None and duration <= 60:
        return True
    return False


def _extract_audio(entry):
    formats = entry.get("formats") or []
    audio_fmts = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]
    if audio_fmts:
        best = audio_fmts[-1]
        url = best.get("url", "")
        ext = best.get("ext", "m4a")
        audio_type = "audio/mp4" if ext == "m4a" else f"audio/{ext}"
        length = best.get("filesize") or best.get("filesize_approx") or 0
        return url, audio_type, length
    return "", "audio/mpeg", 0


def fetch_videos_real(channel_url, num_videos):
    import yt_dlp

    channel_url = channel_url.rstrip("/")
    if not channel_url.endswith("/videos"):
        channel_url += "/videos"

    ydl_opts = {"quiet": True, "extract_flat": False}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    channel_title = info.get("channel", info.get("title", ""))
    entries = info.get("entries", [])
    if not entries:
        print("No videos found.", file=sys.stderr)
        sys.exit(1)

    videos = []
    for entry in entries:
        if len(videos) >= num_videos:
            break
        if _is_short(entry):
            continue

        audio_url, audio_type, length = _extract_audio(entry)

        videos.append({
            "title": entry.get("title", ""),
            "description": entry.get("description") or "",
            "published": entry.get("upload_date", ""),
            "url": f"https://www.youtube.com/watch?v={entry['id']}",
            "video_id": entry["id"],
            "audio_url": audio_url,
            "audio_type": audio_type,
            "length": length,
            "channel_title": channel_title,
        })
    return videos


def load_test_data():
    test_data_path = os.path.join(os.path.dirname(__file__), "test_data.json")
    if not os.path.exists(test_data_path):
        return None
    with open(test_data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_sample_videos():
    return [
        {
            "title": "Understanding Quantum Computing",
            "description": "A deep dive into the world of quantum computing and its implications for the future of technology.",
            "published": "20260315",
            "url": "https://www.youtube.com/watch?v=sample1",
            "video_id": "sample1",
            "audio_url": "https://example.com/audio/sample1.mp3",
            "audio_type": "audio/mpeg",
            "length": 12345678,
            "channel_title": "Sample Channel",
        },
        {
            "title": "Python 3.14 New Features Explained",
            "description": "Exploring the latest features in Python 3.14 including the new pattern matching enhancements.",
            "published": "20260310",
            "url": "https://www.youtube.com/watch?v=sample2",
            "video_id": "sample2",
            "audio_url": "https://example.com/audio/sample2.mp3",
            "audio_type": "audio/mpeg",
            "length": 23456789,
            "channel_title": "Sample Channel",
        },
        {
            "title": "Building CLI Tools in Rust",
            "description": "Step-by-step guide to building fast and reliable command-line tools using Rust.",
            "published": "20260305",
            "url": "https://www.youtube.com/watch?v=sample3",
            "video_id": "sample3",
            "audio_url": "https://example.com/audio/sample3.mp3",
            "audio_type": "audio/mpeg",
            "length": 34567890,
            "channel_title": "Sample Channel",
        },
        {
            "title": "The Future of AI Assistants",
            "description": "A discussion about the evolving landscape of AI-powered assistants and their impact on productivity.",
            "published": "20260228",
            "url": "https://www.youtube.com/watch?v=sample4",
            "video_id": "sample4",
            "audio_url": "https://example.com/audio/sample4.mp3",
            "audio_type": "audio/mpeg",
            "length": 45678901,
            "channel_title": "Sample Channel",
        },
        {
            "title": "Docker for Beginners",
            "description": "Everything you need to know to get started with Docker and containerization.",
            "published": "20260220",
            "url": "https://www.youtube.com/watch?v=sample5",
            "video_id": "sample5",
            "audio_url": "https://example.com/audio/sample5.mp3",
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


def generate_rss(videos, channel_url):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    channel_title = videos[0]["channel_title"] if videos else "YouTube Podcast"
    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = channel_url

    atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
    atom_link.set("href", channel_url)
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    ET.SubElement(channel, "description").text = f"Podcast feed for {channel_title}"

    image = ET.SubElement(channel, "image")
    ET.SubElement(image, "url").text = "https://www.google.com/s2/favicons?domain=youtube.com&sz=128"
    ET.SubElement(image, "title").text = channel_title
    ET.SubElement(image, "link").text = channel_url

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

        if v.get("audio_url"):
            enc = ET.SubElement(item, "enclosure")
            enc.set("url", v["audio_url"])
            enc.set("type", v.get("audio_type", "audio/mpeg"))
            enc.set("length", str(v.get("length", "0")))

    raw = ET.tostring(rss, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + raw


def main():
    args = parse_args()

    channel_url = args.url
    if not channel_url and not args.test:
        config = load_config(args.config)
        channel_url = config.get("channel_url", "")

    if not channel_url and not args.test:
        print("Error: YouTube channel URL required. Provide as argument or set in config.yml.", file=sys.stderr)
        sys.exit(1)

    if args.test:
        data = load_test_data()
        if data:
            videos = data["videos"]
            channel_url = data.get("channel_url", channel_url or "https://youtube.com/@test")
        else:
            videos = generate_sample_videos()
            channel_url = channel_url or "https://youtube.com/@test"
    else:
        videos = fetch_videos_real(channel_url, args.num_videos)

    rss_xml = generate_rss(videos, channel_url)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(rss_xml)

    print(f"Feed written to {args.output} with {len(videos)} items.", file=sys.stderr)


if __name__ == "__main__":
    main()
