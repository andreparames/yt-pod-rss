#!/usr/bin/env python3
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import xml.etree.ElementTree as ET

import generate_feed as gf


class TestFallbackMode(unittest.TestCase):
    """Tests for the non-S3 mode (no storage configured)."""

    def test_init_storage_returns_none_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(gf.init_storage())

    @patch.dict(os.environ, {}, clear=True)
    def test_rss_uses_relative_paths(self, *_):
        videos = gf.generate_sample_videos("testfeed")
        rss = gf.generate_rss(videos, "https://youtube.com/@test", "testfeed")
        root = ET.fromstring(rss)
        for item, v in zip(root.findall(".//item"), videos):
            enc = item.find("enclosure")
            self.assertEqual(enc.get("url"), v["audio_url"])

    def test_rss_is_valid_xml(self):
        videos = gf.generate_sample_videos("testfeed")
        rss = gf.generate_rss(videos, "https://youtube.com/@test", "testfeed")
        root = ET.fromstring(rss)
        self.assertEqual(root.tag, "rss")
        items = root.findall(".//item")
        self.assertEqual(len(items), 5)

    def test_feed_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.xml")
            videos = gf.generate_sample_videos("testfeed")
            gf.write_feed(videos, "https://youtube.com/@test", "testfeed", path)
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                self.assertIn("Understanding Quantum Computing", f.read())

    def test_parse_pub_date_valid(self):
        result = gf.parse_pub_date("20260315")
        self.assertEqual(result, "Sun, 15 Mar 2026 00:00:00 +0000")

    def test_parse_pub_date_empty(self):
        self.assertEqual(gf.parse_pub_date(""), "")

    def test_is_short_by_title(self):
        self.assertTrue(gf._is_short({"title": "My Video #Shorts"}))
        self.assertFalse(gf._is_short({"title": "My Video"}))

    def test_is_short_by_duration(self):
        self.assertTrue(gf._is_short({"duration": 30}))
        self.assertFalse(gf._is_short({"duration": 120}))

    def test_validate_name(self):
        gf.validate_name("valid_name123")
        with self.assertRaises(SystemExit):
            gf.validate_name("invalid name!")

    def test_load_test_data(self):
        data = gf.load_test_data()
        self.assertIsNotNone(data)
        self.assertIn("videos", data)

    def test_generate_sample_videos_structure(self):
        videos = gf.generate_sample_videos("test")
        self.assertEqual(len(videos), 5)
        for v in videos:
            self.assertIn("title", v)
            self.assertIn("audio_url", v)
            self.assertIn("length", v)
            self.assertTrue(v["audio_url"].startswith("media/test/"))


class TestS3Mode(unittest.TestCase):
    """Tests for the S3 storage mode."""

    S3_ENV = {
        "S3_ENDPOINT": "s3.us-east-1.amazonaws.com",
        "S3_REGION": "us-east-1",
        "S3_ACCESS_KEY_ID": "test-key",
        "S3_SECRET_ACCESS_KEY": "test-secret",
        "S3_BUCKET": "my-bucket",
    }

    @patch.dict(os.environ, S3_ENV)
    def test_init_storage_returns_config(self, *_):
        with patch("boto3.Session") as mock_session:
            mock_session.return_value.client.return_value = MagicMock()
            storage = gf.init_storage()
            self.assertIsNotNone(storage)
            self.assertEqual(storage["bucket"], "my-bucket")
            self.assertEqual(storage["endpoint"], "s3.us-east-1.amazonaws.com")
            self.assertEqual(storage["prefix"], "media/")

    def test_init_storage_returns_none_without_endpoint(self):
        with patch.dict(os.environ, {"S3_ACCESS_KEY_ID": "x", "S3_SECRET_ACCESS_KEY": "y",
                                      "S3_BUCKET": "b"}, clear=True):
            self.assertIsNone(gf.init_storage())

    def test_public_url_virtual_hosted(self):
        storage = {"endpoint": "s3.us-east-1.amazonaws.com", "bucket": "my-bucket",
                   "path_style": False}
        url = gf.public_url(storage, "media/feed/video.m4a")
        self.assertEqual(url, "https://my-bucket.s3.us-east-1.amazonaws.com/media/feed/video.m4a")

    def test_public_url_path_style(self):
        storage = {"endpoint": "minio.example.com", "bucket": "my-bucket",
                   "path_style": True}
        url = gf.public_url(storage, "media/feed/video.m4a")
        self.assertEqual(url, "https://minio.example.com/my-bucket/media/feed/video.m4a")

    @patch.dict(os.environ, S3_ENV)
    def test_check_storage_found(self, *_):
        mock_s3 = MagicMock()
        mock_s3.head_object.return_value = {"ContentLength": 12345}
        storage = {"client": mock_s3, "bucket": "b", "prefix": "media/"}
        key, size, ext = gf.check_storage(storage, "podcast", "abc123")
        self.assertEqual(key, "media/podcast/abc123.m4a")
        self.assertEqual(size, 12345)
        self.assertEqual(ext, "m4a")
        mock_s3.head_object.assert_called_with(Bucket="b", Key="media/podcast/abc123.m4a")

    @patch.dict(os.environ, S3_ENV)
    def test_check_storage_not_found(self, *_):
        from botocore.exceptions import ClientError
        mock_s3 = MagicMock()
        error = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        mock_s3.head_object.side_effect = error
        storage = {"client": mock_s3, "bucket": "b", "prefix": "media/"}
        key, size, ext = gf.check_storage(storage, "podcast", "abc123")
        self.assertIsNone(key)
        self.assertEqual(size, 0)
        self.assertIsNone(ext)

    @patch.dict(os.environ, S3_ENV)
    def test_check_storage_tries_multiple_extensions(self, *_):
        from botocore.exceptions import ClientError
        mock_s3 = MagicMock()
        error = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        mock_s3.head_object.side_effect = [
            error,  # m4a
            error,  # mp3
            {"ContentLength": 9999},  # webm found
        ]
        storage = {"client": mock_s3, "bucket": "b", "prefix": "media/"}
        key, size, ext = gf.check_storage(storage, "podcast", "abc123")
        self.assertEqual(key, "media/podcast/abc123.webm")
        self.assertEqual(size, 9999)
        self.assertEqual(ext, "webm")

    @patch.dict(os.environ, S3_ENV)
    def test_upload_to_storage(self, *_):
        mock_s3 = MagicMock()
        storage = {"client": mock_s3, "bucket": "b", "prefix": "media/"}
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"test data")
            f.flush()
            gf.upload_to_storage(storage, f.name, "media/podcast/abc123.m4a")
        mock_s3.upload_file.assert_called_with(f.name, "b", "media/podcast/abc123.m4a")


class TestEndToEnd(unittest.TestCase):
    """End-to-end tests using --test mode (exercises RSS generation)."""

    def test_test_mode_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig_dir = os.getcwd()
            os.chdir(tmp)
            try:
                with patch.object(sys, "argv", ["generate_feed.py", "--test"]):
                    gf.main()
                self.assertTrue(os.path.exists("test.xml"))
            finally:
                os.chdir(orig_dir)

    def test_test_mode_named_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            orig_dir = os.getcwd()
            os.chdir(tmp)
            try:
                with patch.object(sys, "argv", ["generate_feed.py", "--test", "mypod"]):
                    gf.main()
                self.assertTrue(os.path.exists("mypod.xml"))
            finally:
                os.chdir(orig_dir)


if __name__ == "__main__":
    unittest.main()
