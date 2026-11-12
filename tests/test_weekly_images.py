"""Weekly image behavior checks with generated images and mocked HTTP only."""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "addons/ai-frontier-weekly/scripts"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = load("weekly_fetch_images", "fetch_images.py")
verify = load("weekly_verify_images", "verify_images.py")


def image_bytes(size=(500, 320)):
    image_type = fetch.pillow_image()
    if image_type is None:
        raise unittest.SkipTest("Optional Pillow is unavailable")
    image = image_type.new("RGB", size, "#b9d3ef")
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


class Response:
    def __init__(self, blob, url, ctype="image/png", status=200):
        self.blob, self.url, self.headers, self.status = blob, url, {"Content-Type": ctype}, status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count=-1):
        return self.blob if count < 0 else self.blob[:count]

    def geturl(self):
        return self.url


class WeeklyImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="weekly-images-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Tests never resolve a real hostname or make an HTTP connection.
        self.network_guard = mock.patch("socket.getaddrinfo", side_effect=AssertionError("Unexpected real DNS"))
        self.http_guard = mock.patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Unexpected real HTTP"))
        self.network_guard.start()
        self.http_guard.start()
        self.addCleanup(mock.patch.stopall)

    def candidate_file(self):
        path = self.root / "candidates.json"
        path.write_text(json.dumps([{"url": "https://news.example.com/story", "source": "示例源", "entry": "示例事件"}]), encoding="utf-8")
        return path

    def fetch_args(self, *extra):
        return ["--candidates", str(self.candidate_file()), "--out-dir", str(self.root / "assets"), "--prefix", "20261116", *extra]

    def local_page(self, source="assets/photo.png", blob=None):
        html = self.root / "index.html"
        html.write_text(f'<html><img src="{source}"></html>', encoding="utf-8")
        target = self.root / "assets/photo.png"
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(image_bytes() if blob is None else blob)
        return html

    def quiet(self, function, *args):
        with redirect_stdout(io.StringIO()) as out:
            result = function(*args)
        return result, out.getvalue()

    def test_domain_boundaries_do_not_treat_public_suffix_or_cdn_lookalikes_as_same_site(self):
        for image, article in [("https://b.co.uk/x", "https://a.co.uk/x"),
                               ("https://b.com.cn/x", "https://a.com.cn/x"),
                               ("https://evilqpic.cn/x", "https://news.example.com/x"),
                               ("https://qpic.cn.evil.com/x", "https://news.example.com/x")]:
            self.assertFalse(fetch.domain_ok(image, article)[0])
        self.assertTrue(fetch.domain_ok("https://cdn.qpic.cn/x", "https://news.example.com/x")[0])
        self.assertTrue(fetch.domain_ok("https://images.news.example.com/x", "https://news.example.com/x")[0])
        self.assertTrue(fetch.domain_ok("https://official.example.net/x", "https://news.example.com/x", {"official.example.net"})[0])

    def test_public_url_rejects_non_network_urls_and_private_resolution(self):
        for url in ("file:///C:/secret", "data:image/png;base64,abc", "http://localhost/a", "https://user:password@example.com/a"):
            with self.assertRaises(ValueError):
                fetch.public_url(url)
        local = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        with mock.patch("socket.getaddrinfo", return_value=local):
            with self.assertRaises(ValueError):
                fetch.public_url("https://internal.example.com/a")

    def test_redirect_handler_checks_target_before_returning_request(self):
        seen = []
        def check(url):
            seen.append(url)
            raise ValueError("blocked redirect")
        handler = fetch.CheckedRedirect(check)
        with self.assertRaises(ValueError):
            handler.redirect_request(urllib.request.Request("https://example.com/a"), None, 302, "Found", {}, "http://127.0.0.1/secret")
        self.assertEqual(seen, ["http://127.0.0.1/secret"])

    def test_download_rechecks_image_provenance_after_redirect(self):
        def redirected(url, referer, url_check=None):
            url_check("https://unrelated.example.org/photo.jpg")
            self.fail("provenance gate should reject before consuming the image")
        with mock.patch.object(fetch, "http_get", side_effect=redirected):
            with self.assertRaises(ValueError):
                fetch.download_image("https://news.example.com/photo.jpg", "https://news.example.com/story", SimpleNamespace(allow_hosts=set(), min_width=400, max_width=1000))

    def test_real_image_is_saved_with_provenance_manifest_and_size_limit(self):
        blob = image_bytes((1200, 720))
        def get(url, referer=None, timeout=25, url_check=None):
            if url.endswith("/story"):
                # Relative picture must resolve against the final article URL.
                return b'<meta content="photo.png" property="og:image">', "text/html", "https://news.example.com/updated/story"
            self.assertEqual(url, "https://news.example.com/updated/photo.png")
            url_check(url)
            return blob, "image/png", url
        with mock.patch.object(fetch, "http_get", side_effect=get):
            result, _ = self.quiet(fetch.main, self.fetch_args("--max-kb", "10"))
        self.assertEqual(result, 0)
        manifest = json.loads((self.root / "assets/manifest-20261116.json").read_text(encoding="utf-8"))
        item = manifest[0]
        self.assertEqual(item["reason"], "ok")
        self.assertEqual(item["article_final_url"], "https://news.example.com/updated/story")
        self.assertTrue(item["image_url"].endswith("/updated/photo.png"))
        saved = self.root / item["file"]
        self.assertLessEqual(saved.stat().st_size, 10 * 1024)
        self.assertLessEqual(verify.decode_image(saved.read_bytes())[0], 1000)

    def test_missing_pillow_writes_no_image_manifest_without_network(self):
        with mock.patch.object(fetch, "pillow_image", return_value=None), mock.patch.object(fetch, "http_get", side_effect=AssertionError("no fetch without image dependency")):
            result, output = self.quiet(fetch.main, self.fetch_args())
        self.assertEqual(result, 0)
        item = json.loads((self.root / "assets/manifest-20261116.json").read_text(encoding="utf-8"))[0]
        self.assertIsNone(item["file"])
        self.assertIn("Pillow", item["reason"])
        self.assertIn("无图", output)

    def test_oversized_output_is_not_reported_as_accepted(self):
        image_type = fetch.pillow_image()
        if image_type is None:
            self.skipTest("Optional Pillow is unavailable")
        image = image_type.frombytes("RGB", (400, 400), bytes((i * 37 + i // 11) % 256 for i in range(400 * 400 * 3)))
        encoded, _ = fetch.encode_image(image, 1, 400)
        self.assertIsNone(encoded)

    def test_prefix_escape_is_rejected_before_output_directory_creation(self):
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                fetch.main(self.fetch_args("--prefix", "../outside"))
        self.assertFalse((self.root / "assets").exists())

    def test_local_checker_decodes_images_instead_of_accepting_nonempty_files(self):
        html = self.local_page(blob=b"not an image" * 400)
        self.assertEqual(self.quiet(verify.main, ["--html", str(html)])[0], 1)
        (self.root / "assets/photo.png").write_bytes(image_bytes())
        self.assertEqual(self.quiet(verify.main, ["--html", str(html)])[0], 0)

    def test_external_encoded_and_missing_src_images_fail_without_network(self):
        html = self.local_page()
        for source in ("https://outside.example.com/photo.jpg", "//outside.example.com/photo.jpg", "data:image/png;base64,abc", "../photo.jpg", "%2e%2e/photo.jpg", "/assets/photo.png", "C:/photo.jpg"):
            html.write_text(f'<img src="{source}">', encoding="utf-8")
            self.assertEqual(self.quiet(verify.main, ["--html", str(html), "--base", "https://example.com"])[0], 1, source)
        html.write_text('<img data-src="assets/photo.png">', encoding="utf-8")
        self.assertEqual(self.quiet(verify.main, ["--html", str(html)])[0], 1)
        html.write_text('<img src="assets/photo.png" srcset="https://outside.example.com/a.jpg 2x">', encoding="utf-8")
        self.assertEqual(self.quiet(verify.main, ["--html", str(html)])[0], 1)
        html.write_text('<picture><source srcset="https://outside.example.com/a.jpg"></picture>', encoding="utf-8")
        self.assertEqual(self.quiet(verify.main, ["--html", str(html)])[0], 1)

    def test_zero_images_is_explicitly_offline_and_needs_no_pillow(self):
        html = self.root / "index.html"
        html.write_text("<p>本期无图，来源未提供可用配图。</p>", encoding="utf-8")
        with mock.patch.object(verify.network, "pillow_image", return_value=None), mock.patch.object(verify, "build_opener", side_effect=AssertionError("no online verification for zero images")):
            result, output = self.quiet(verify.main, ["--html", str(html), "--base", "https://example.com"])
        self.assertEqual(result, 0)
        self.assertIn("未进行线上", output)

    def test_online_checker_rejects_nonimage_bytes_and_never_forwards_sharecode(self):
        html = self.local_page()
        requests = []
        bad_image = [False]
        class FakeOpener:
            def open(self, request, timeout=25):
                requests.append(request)
                url = request.full_url
                if "sharecode=" in url:
                    return Response(b"<html>site</html>", "https://example.com/", "text/html")
                self_url = "https://example.com/assets/photo.png"
                return Response(b"wrong bytes" if bad_image[0] else image_bytes(), self_url)
        with mock.patch.object(verify.network, "public_url", return_value=urllib.parse.urlsplit("https://example.com/")), mock.patch.object(verify, "build_opener", return_value=FakeOpener()):
            result, output = self.quiet(verify.main, ["--html", str(html), "--base", "https://example.com", "--sharecode", "PRIVATE_TEST_CODE"])
            self.assertEqual(result, 0)
            self.assertNotIn("PRIVATE_TEST_CODE", output)
            self.assertEqual(requests[-1].get_header("Referer"), "https://example.com/")
            self.assertNotIn("PRIVATE_TEST_CODE", requests[-1].full_url)
            bad_image[0] = True
            self.assertEqual(self.quiet(verify.main, ["--html", str(html), "--base", "https://example.com"])[0], 1)


if __name__ == "__main__":
    unittest.main()
