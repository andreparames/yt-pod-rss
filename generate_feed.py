#!/usr/bin/env python3
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.sax.saxutils import escape

ET.register_namespace("atom", "http://www.w3.org/2005/Atom")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate an RSS 2.0 podcast feed from a YouTube channel.")
    parser.add_argument("url", nargs="?", help="YouTube channel URL")
    parser.add_argument("-o", "--output", default="feed.xml", help="Output RSS file (default: feed.xml)")
    parser.add_argument("-n", "--num-videos", type=int, default=20, help="Number of recent videos (default: 20)")
    parser.add_argument("--test", action="store_true", help="Use sample test data instead of YouTube")
    return parser.parse_args()


def fetch_videos_real(channel_url, num_videos):
    import yt_dlp
    ydl_opts = {"quiet": True, "extract_flat": "in_playlist"}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    channel_title = info.get("channel", info.get("title", ""))
    entries = info.get("entries", [])
    if not entries:
        print("No videos found.", file=sys.stderr)
        sys.exit(1)

    videos = []
    full_ydl = yt_dlp.YoutubeDL({"quiet": True})
    for i, entry in enumerate(entries[:num_videos]):
        vid = entry["id"]
        print(f"[{i+1}/{min(num_videos, len(entries))}] Fetching {vid}...", file=sys.stderr)
        try:
            vinfo = full_ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
        except Exception as e:
            print(f"  Skipping {vid}: {e}", file=sys.stderr)
            continue

        audio_url = None
        audio_type = "audio/mp4"
        length = 0
        if vinfo.get("formats"):
            audio_fmts = [f for f in vinfo["formats"] if f.get("vcodec") == "none" and f.get("acodec") != "none"]
            if audio_fmts:
                best = audio_fmts[-1]
                audio_url = best.get("url") or audio_url
                ext = best.get("ext", "m4a")
                audio_type = f"audio/{ext}"
                audio_type = audio_type.replace("audio/m4a", "audio/mp4")
                length = best.get("filesize") or best.get("filesize_approx") or 0
            else:
                any_audio = [f for f in vinfo["formats"] if f.get("acodec") != "none"]
                if any_audio:
                    best = any_audio[-1]
                    audio_url = best.get("url") or audio_url
                    ext = best.get("ext", "mp4")
                    audio_type = f"audio/{ext}"
                    audio_type = audio_type.replace("audio/m4a", "audio/mp4")
                    length = best.get("filesize") or best.get("filesize_approx") or 0

        videos.append({
            "title": vinfo.get("title", entry.get("title", "")),
            "description": vinfo.get("description", ""),
            "published": vinfo.get("upload_date") or entry.get("upload_date", ""),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "video_id": vid,
            "audio_url": audio_url or "",
            "audio_type": audio_type,
            "length": length,
            "channel_title": channel_title,
        })
    return videos


def load_test_data():
    test_data_path = os.path.join(os.path.dirname(__file__), "test_data.json")
    if not os.path.exists(test_data_path):
        print("Test data file not found. Generating inline sample data.", file=sys.stderr)
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
    ET.SubElement(channel, "description").text = f"Podcast feed generated from {channel_url}"

    atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
    atom_link.set("href", channel_url)
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    image = ET.SubElement(channel, "image")
    ET.SubElement(image, "url").text = f"https://www.google.com/s2/favicons?domain=youtube.com&sz=128"
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

    channel_url = args.url or os.environ.get("YT_CHANNEL_URL", "")
    if not channel_url and not args.test:
        print("Error: YouTube channel URL required (provide as argument or set YT_CHANNEL_URL env var)", file=sys.stderr)
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
