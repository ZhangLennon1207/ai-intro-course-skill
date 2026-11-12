#!/usr/bin/env python3
"""周报原文配图本地化；无合格图片时写入无图原因，不补装饰图。

python fetch_images.py --candidates cand.json --out-dir weekly-site/assets --prefix 20261116
候选格式：[{"url": "https://example.com/article", "source": "来源", "entry": "标题"}]
Pillow是可选配图依赖；缺失时输出无图manifest，周报正文仍可继续。
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import io
import ipaddress
import json
from pathlib import Path
import re
import socket
import sys
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
MIN_WIDTH, MAX_WIDTH, MAX_BYTES_KB, JPEG_QUALITY = 400, 1000, 250, 82
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
BAD_TOKENS = ("logo", "banner", "qrcode", "qr_", "avatar", "icon", "sprite", "share",
              "default", "placeholder", "badge", "watermark", "emoji", "favicon", "loading")
CDN_SUFFIXES = ("qpic.cn", "sinaimg.cn", "ifengimg.com", "cnbcfm.com", "cloudfront.net",
                "alicdn.com", "byteimg.com", "hdslb.com", "wp.com", "ggpht.com", "twimg.com",
                "medium.com", "ctfassets.net", "storage.googleapis.com", "githubusercontent.com")


def log(message):
    print(message, flush=True)


def safe_display(url):
    """Avoid printing signed query strings or URL credentials."""
    parsed = urllib.parse.urlsplit(url)
    return f"{parsed.scheme}://{parsed.hostname or ''}{parsed.path}"


def public_url(url):
    """Accept only public HTTP(S) targets, including each redirect destination."""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme.lower() not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or any(c in url for c in "\r\n\x00")):
        raise ValueError("仅接受不含账号信息的公开HTTP(S)地址")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError("不访问本机或局域网地址")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("地址解析到非公开网络")
    return parsed


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, check):
        super().__init__()
        self.check = check

    def redirect_request(self, request, fp, code, message, headers, newurl):
        self.check(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def http_get(url, referer=None, timeout=25, url_check=None):
    def check(target):
        public_url(target)
        if url_check:
            url_check(target)
    check(url)
    headers = {"User-Agent": UA, "Accept": "text/html,image/*,*/*", "Accept-Encoding": "identity"}
    if referer:
        headers["Referer"] = root_of(referer)
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(CheckedRedirect(check))
    with opener.open(request, timeout=timeout) as response:
        final_url = response.geturl()
        check(final_url)
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("响应超过20MB，未采用")
        return data, response.headers.get("Content-Type", ""), final_url


def root_of(url):
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def domain_ok(img_url, article_url, allow_hosts=()):
    """Conservative host relationship; do not guess public suffix boundaries."""
    try:
        image = (urllib.parse.urlsplit(img_url).hostname or "").lower().rstrip(".")
        article = (urllib.parse.urlsplit(article_url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False, "域名解析失败"
    if not image or not article:
        return False, "地址无域名"
    if image == article or image.endswith("." + article):
        return True, "文章同站或其子域"
    if image in allow_hosts:
        return True, "指定官方CDN"
    if any(image == suffix or image.endswith("." + suffix) for suffix in CDN_SUFFIXES):
        return True, "已知CDN；仍须由原文引用"
    return False, "跨站图片；需要确认官方CDN后显式放行"


def bad_name(url):
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path).lower()
    return next((f"路径含 '{token}'" for token in BAD_TOKENS if token in path), None)


class ArticleImages(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.inline = [], []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag.lower() == "meta":
            name = (values.get("property") or values.get("name") or "").lower()
            if name in ("og:image", "og:image:url", "twitter:image") and values.get("content"):
                self.meta.append(("meta:" + name, values["content"]))
        elif tag.lower() == "img" and len(self.inline) < 30:
            source = values.get("data-src") or values.get("data-original") or values.get("src")
            if source:
                self.inline.append(("inline", source))


def find_images(html, article_url):
    parser = ArticleImages()
    parser.feed(html)
    seen, result = set(), []
    for kind, value in parser.meta + parser.inline:
        url = urllib.parse.urljoin(article_url, value.strip())
        if urllib.parse.urlsplit(url).scheme.lower() not in ("http", "https") or url in seen:
            continue
        seen.add(url)
        result.append((kind, url))
    return result


def pillow_image():
    try:
        from PIL import Image
        return Image
    except ImportError:
        return None


def download_image(url, article_url, opts):
    def provenance(target):
        allowed, reason = domain_ok(target, article_url, opts.allow_hosts)
        if not allowed or bad_name(target):
            raise ValueError(reason if not allowed else bad_name(target))
    data, content_type, final_url = http_get(url, article_url, url_check=provenance)
    if not content_type.lower().startswith("image/"):
        return None, "Content-Type非图片", final_url
    image_type = pillow_image()
    if image_type is None:
        return None, "缺少Pillow配图依赖", final_url
    try:
        image = image_type.open(io.BytesIO(data))
        if image.width * image.height > 40_000_000:
            return None, "图片像素超过40MP", final_url
        image.load()
    except Exception as exc:
        return None, f"无法解析图片({type(exc).__name__})", final_url
    original = image.size
    if image.width < opts.min_width:
        return None, f"宽度{image.width}px不足{opts.min_width}px", final_url
    if image.width > opts.max_width:
        image = image.resize((opts.max_width, max(1, round(image.height * opts.max_width / image.width))), image_type.Resampling.LANCZOS)
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        image = image_type.new("RGB", image.size, "white")
        image.paste(rgba, mask=rgba.getchannel("A"))
    else:
        image = image.convert("RGB")
    return image, f"{original[0]}x{original[1]}", final_url


def encode_image(image, max_kb, min_width):
    """Return accepted JPEG bytes or None; never label oversized output as ok."""
    image_type = pillow_image()
    while True:
        for quality in (JPEG_QUALITY, 72, 62, 52, 42):
            stream = io.BytesIO()
            image.save(stream, "JPEG", quality=quality, optimize=True, progressive=True)
            blob = stream.getvalue()
            if len(blob) <= max_kb * 1024:
                return blob, image.size
        if image.width <= min_width:
            return None, image.size
        width = max(min_width, int(image.width * 0.8))
        image = image.resize((width, max(1, round(image.height * width / image.width))), image_type.Resampling.LANCZOS)


def main(argv=None):
    parser = argparse.ArgumentParser(description="周报原文配图本地化")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--max-per-entry", type=int, choices=(1,), default=1)
    parser.add_argument("--min-width", type=int, default=MIN_WIDTH)
    parser.add_argument("--max-width", type=int, default=MAX_WIDTH)
    parser.add_argument("--max-kb", type=int, default=MAX_BYTES_KB)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--allow-hosts", default="", help="已确认的官方CDN主机，逗号分隔")
    opts = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", opts.prefix):
        parser.error("prefix只能包含字母、数字、下划线和连字符，不能包含路径")
    if opts.min_width < 1 or opts.max_width < opts.min_width or opts.max_kb < 1:
        parser.error("图片尺寸或大小限制无效")
    opts.allow_hosts = {value.strip().lower().rstrip(".") for value in opts.allow_hosts.split(",") if value.strip()}
    candidates = json.loads(Path(opts.candidates).read_text(encoding="utf-8-sig"))
    if not isinstance(candidates, list) or not all(isinstance(item, dict) for item in candidates):
        parser.error("候选文件必须是对象数组")
    results, picked = [], 0
    have_pillow = pillow_image() is not None
    output = Path(opts.out_dir)
    if not opts.dry_run:
        output.mkdir(parents=True, exist_ok=True)
    for item in candidates:
        article = item.get("url", "")
        record = {"entry": item.get("entry", ""), "source": item.get("source", ""), "article": article,
                  "file": None, "image_url": None, "reason": ""}
        if not have_pillow:
            record["reason"] = "缺少可选Pillow配图依赖；本条不配图，正文可继续"
        elif not isinstance(article, str) or not article:
            record["reason"] = "缺原文地址"
        else:
            try:
                html, content_type, final_article = http_get(article)
                if "html" not in content_type.lower():
                    raise ValueError("原文不是HTML页面")
                record["article_final_url"] = final_article
                for kind, image_url in find_images(html.decode("utf-8", "replace"), final_article):
                    allowed, _ = domain_ok(image_url, final_article, opts.allow_hosts)
                    if not allowed or bad_name(image_url):
                        continue
                    try:
                        image, detail, final_image = download_image(image_url, final_article, opts)
                        if image is None:
                            continue
                        encoded, size = encode_image(image, opts.max_kb, opts.min_width)
                        if encoded is None:
                            continue
                    except Exception:
                        continue
                    picked += 1
                    filename = f"{opts.prefix}-{picked}.jpg"
                    if not opts.dry_run:
                        (output / filename).write_bytes(encoded)
                    record.update(file="assets/" + filename, image_url=final_image, size=f"{size[0]}x{size[1]}",
                                  kb=round(len(encoded) / 1024, 2), source_size=detail, **{"from": kind}, reason="ok")
                    break
                if not record["file"]:
                    record["reason"] = "无满足来源、尺寸与大小限制的原文图片"
            except Exception as exc:
                record["reason"] = f"原文获取或校验失败({type(exc).__name__})"
        results.append(record)
        log(f"[{'采用' if record['file'] else '无图'}] {record['entry']}：{record['file'] or record['reason']}")
    manifest = Path(opts.manifest) if opts.manifest else output / f"manifest-{opts.prefix}.json"
    if not opts.dry_run:
        manifest.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"汇总：候选{len(results)}条，配到{picked}条，无图{len(results) - picked}条")
    if not have_pillow:
        log("可选配图依赖缺失：可在本项目环境安装requirements.txt；不要伪称取图成功。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
