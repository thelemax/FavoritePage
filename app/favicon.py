"""Récupération des favicons côté serveur + cache disque.

Le serveur (dans le LAN) récupère l'icône du site : balises <link rel="icon"> de la page d'accueil,
sinon /favicon.ico. Le résultat est mis en cache dans config/cache/favicons ; un échec est mémorisé
(fichier .none) et retenté après RETRY_AFTER secondes. Vider le dossier force un rechargement.
Certificats non vérifiés : usage LAN avec certificats auto-signés fréquents (Proxmox, TrueNAS...).
"""
from __future__ import annotations

import hashlib
import os
import re
import ssl
import tempfile
import threading
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urljoin, urlparse

TIMEOUT = 4
MAX_BYTES = 512 * 1024
RETRY_AFTER = 24 * 3600
USER_AGENT = "Mozilla/5.0 (FavoritePage favicon fetcher)"

MEDIA = {".png": "image/png", ".ico": "image/x-icon", ".svg": "image/svg+xml", ".jpg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp"}
_CTYPE_EXT = {"image/png": ".png", "image/x-icon": ".ico", "image/vnd.microsoft.icon": ".ico",
              "image/svg+xml": ".svg", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


class _IconParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.icons: list[tuple[str, str, str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = {k: (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower()
        if a.get("href") and "icon" in rel and "mask" not in rel:
            self.icons.append((rel, a["href"], a.get("type", "").lower(), a.get("sizes", "").lower()))


def _score(icon: tuple[str, str, str, str]) -> int:
    rel, href, typ, sizes = icon
    if "svg" in typ or href.lower().split("?")[0].endswith(".svg") or sizes == "any":
        return 512
    nums = [int(n) for n in re.findall(r"\d+", sizes)]
    if nums:
        return max(nums)
    return 180 if "apple-touch" in rel else 32


def _get(url: str) -> tuple[str, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL) as r:
        return r.geturl(), r.headers.get_content_type(), r.read(MAX_BYTES)


def _sniff(data: bytes, ctype: str) -> Optional[str]:
    head = data[:512].lstrip()
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"\x00\x00\x01\x00"):
        return ".ico"
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data.startswith(b"GIF8"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if b"<svg" in data[:2048].lower() and (head.startswith(b"<svg") or head.startswith(b"<?xml") or ctype == "image/svg+xml"):
        return ".svg"
    if ctype in _CTYPE_EXT and ctype != "image/svg+xml":
        return _CTYPE_EXT[ctype]
    return None


def _candidates(origin: str) -> Iterator[str]:
    base = origin + "/"
    try:
        final, ctype, body = _get(base)
        if ctype in ("text/html", "application/xhtml+xml"):
            parser = _IconParser()
            parser.feed(body.decode("utf-8", "ignore"))
            for icon in sorted(parser.icons, key=_score, reverse=True):
                yield urljoin(final, icon[1])
            base = final
    except Exception:
        pass
    yield urljoin(base, "/favicon.ico")
    if urlparse(base).netloc != urlparse(origin).netloc:
        yield origin + "/favicon.ico"


class FaviconCache:
    def __init__(self, cache_dir: Path) -> None:
        self.dir = cache_dir
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def _cached(self, key: str) -> Optional[tuple[Path, str]] | bool:
        for f in self.dir.glob(key + ".*"):
            if f.suffix == ".none":
                if time.time() - f.stat().st_mtime < RETRY_AFTER:
                    return False
                f.unlink(missing_ok=True)
            elif f.suffix in MEDIA:
                return f, MEDIA[f.suffix]
        return None

    def get(self, url: str) -> Optional[tuple[Path, str]]:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return None
        origin = f"{p.scheme}://{p.netloc}"
        key = re.sub(r"[^a-z0-9.-]", "_", p.netloc.lower())[:80] + "-" + hashlib.sha1(origin.encode()).hexdigest()[:8]

        with self._lock(key):
            hit = self._cached(key)
            if hit is False:
                return None
            if hit:
                return hit
            self.dir.mkdir(parents=True, exist_ok=True)
            seen = set()
            for cand in _candidates(origin):
                if cand in seen:
                    continue
                seen.add(cand)
                try:
                    _, ctype, data = _get(cand)
                except Exception:
                    continue
                ext = _sniff(data, ctype) if data else None
                if ext:
                    target = self.dir / (key + ext)
                    fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
                    with os.fdopen(fd, "wb") as f:
                        f.write(data)
                    os.replace(tmp, target)
                    return target, MEDIA[ext]
            (self.dir / (key + ".none")).touch()
            return None

