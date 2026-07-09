#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ET.register_namespace("atom", "http://www.w3.org/2005/Atom")

NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


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


def init_storage():
    endpoint = os.environ.get("S3_ENDPOINT")
    if not endpoint:
        return None
    import boto3
    session = boto3.Session(
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("S3_REGION"),
    )
    path_style = os.environ.get("S3_PATH_STYLE", "").lower() in ("1", "true", "yes")
    client = session.client(
        "s3",
        endpoint_url=f"https://{endpoint}",
        config=boto3.session.Config(s3={"addressing_style": "path" if path_style else "virtual"}),
    )
    bucket = os.environ["S3_BUCKET"]
    prefix = os.environ.get("S3_PREFIX", "media/").strip("/") + "/"
    return {"client": client, "bucket": bucket, "prefix": prefix, "endpoint": endpoint,
            "path_style": path_style}


def public_url(storage, key):
    if storage["path_style"]:
        return f"https://{storage['endpoint']}/{storage['bucket']}/{key}"
    return f"https://{storage['bucket']}.{storage['endpoint']}/{key}"


def upload_to_storage(storage, filepath, key):
    import botocore
    try:
        storage["client"].head_object(Bucket=storage["bucket"], Key=key)
        return
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] != "404":
            raise
    print(f"  Uploading to S3...", file=sys.stderr)
    storage["client"].upload_file(filepath, storage["bucket"], key)


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
    return info, rel_path, mime, size, filepath


def process_channel(name, channel_url, num_videos, player_client=None, storage=None):
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
    for entry in entries:
        if len(videos) >= num_videos:
            break
        if _is_short(entry):
            continue

        vid = entry["id"]
        print(f"  Downloading {vid}...", file=sys.stderr)
        try:
            vinfo, rel_path, mime, size, filepath = download_audio(vid, media_dir, name, player_client)
        except Exception as e:
            print(f"  Error downloading {vid}: {e}", file=sys.stderr)
            continue

        audio_url = rel_path
        if storage:
            key = f"{storage['prefix']}{name}/{vid}.{filepath.rsplit('.', 1)[-1]}"
            upload_to_storage(storage, filepath, key)
            audio_url = public_url(storage, key)

        videos.append({
            "title": vinfo.get("title", entry.get("title", "")),
            "description": vinfo.get("description") or entry.get("description", ""),
            "published": vinfo.get("upload_date") or entry.get("upload_date", ""),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "video_id": vid,
            "audio_url": audio_url,
            "audio_type": mime,
            "length": size,
            "channel_title": channel_title,
        })
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


def generate_rss(videos, channel_url, name):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    channel_title = videos[0]["channel_title"] if videos else name
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


def write_feed(videos, channel_url, name, output_path):
    rss_xml = generate_rss(videos, channel_url, name)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rss_xml)
    print(f"  Written {output_path} with {len(videos)} items.", file=sys.stderr)


def main():
    args = parse_args()
    storage = init_storage()

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
        videos = process_channel(feed_name, args.url, args.num_videos, client, storage)
        write_feed(videos, args.url, feed_name, output)
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
        videos = process_channel(name, url, num, player_client=client, storage=storage)
        write_feed(videos, url, name, output)


if __name__ == "__main__":
    main()
