"""Lecture / écriture des fichiers YAML de configuration.

- data.yaml  : colonnes / catégories / liens.
- theme.yaml : apparence (voir models.Theme).
- Les fichiers sont relus à chaque accès (éditions manuelles prises en compte immédiatement).
- Écritures protégées par un verrou et atomiques (fichier temporaire + os.replace).
- ruamel.yaml (round-trip) préserve ordre des clés, commentaires et clés inconnues.
- Concurrence avec une édition manuelle : "last write wins".
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

from .models import Theme

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "data.yaml"
DATA_FILE = Path(os.environ.get("DATA_FILE") or _DEFAULT_PATH)
CONFIG_DIR = DATA_FILE.parent
THEME_FILE = Path(os.environ.get("THEME_FILE") or CONFIG_DIR / "theme.yaml")
FONDS_DIR = CONFIG_DIR / "fonds"
ICONS_DIR = CONFIG_DIR / "icons"
CACHE_DIR = CONFIG_DIR / "cache" / "favicons"

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"}

_lock = threading.RLock()
_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)
_yaml.width = 4096


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class StorageError(Exception):
    pass


# --------------------------------------------------------------------------- I/O

def _load(path: Path) -> CommentedMap:
    try:
        with path.open("r", encoding="utf-8") as f:
            doc = _yaml.load(f)
    except YAMLError as e:
        raise StorageError(f"{path.name} invalide : {e}") from e
    if doc is None:
        doc = CommentedMap()
    if not isinstance(doc, dict):
        raise StorageError(f"{path.name} : la racine doit être un dictionnaire")
    return doc


def _write(path: Path, doc: CommentedMap) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            _yaml.dump(doc, f)
        mode = path.stat().st_mode if path.exists() else 0o644
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _to_cm(value: Any) -> Any:
    """dict/list Python -> structures ruamel (pour un rendu YAML propre)."""
    if isinstance(value, dict):
        return CommentedMap((k, _to_cm(v)) for k, v in value.items())
    if isinstance(value, list):
        return CommentedSeq(_to_cm(v) for v in value)
    return value


def _merge(dst: CommentedMap, src: dict) -> None:
    """Met à jour dst avec src en conservant commentaires et clés inconnues."""
    for k, v in src.items():
        if isinstance(v, dict):
            if not isinstance(dst.get(k), dict):
                dst[k] = CommentedMap()
            _merge(dst[k], v)
        else:
            dst[k] = v


def _default_data() -> CommentedMap:
    doc = CommentedMap()
    doc["columns"] = CommentedSeq(CommentedMap(categories=CommentedSeq()) for _ in range(3))
    return doc


def _read_data() -> CommentedMap:
    if not DATA_FILE.exists():
        doc = _default_data()
        _write(DATA_FILE, doc)
        return doc
    return _load(DATA_FILE)


def _read_theme_doc() -> CommentedMap:
    if not THEME_FILE.exists():
        doc = _to_cm(Theme().model_dump())
        _write(THEME_FILE, doc)
        return doc
    return _load(THEME_FILE)


def _theme_from_doc(doc: dict) -> dict:
    try:
        return Theme.model_validate(doc).model_dump()
    except ValidationError as e:
        err = e.errors()[0]
        where = ".".join(str(p) for p in err["loc"])
        raise StorageError(f"{THEME_FILE.name} invalide ({where}) : {err['msg']}") from e


# ------------------------------------------------------------------ initialisation

def init() -> None:
    """Crée les dossiers et migre l'ancien `background`/`theme` de data.yaml vers theme.yaml."""
    for d in (FONDS_DIR, ICONS_DIR, CACHE_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    with _lock:
        doc = _read_data()
        if "background" not in doc and "theme" not in doc:
            return
        if not THEME_FILE.exists():
            theme = Theme().model_dump()
            legacy = doc.get("background")
            if isinstance(legacy, dict):
                theme["background"]["image"] = str(legacy.get("image") or "")
                theme["background"]["attachment"] = "fixed" if legacy.get("mode", "fixed") == "fixed" else "scroll"
            theme["columns"] = max(1, min(6, len(_seq(doc, "columns")) or 3))
            _write(THEME_FILE, _to_cm(theme))
        doc.pop("background", None)
        doc.pop("theme", None)
        _write(DATA_FILE, doc)


# ------------------------------------------------------------------ navigation

def _seq(parent: dict, key: str) -> CommentedSeq:
    value = parent.get(key)
    if not isinstance(value, list):
        value = CommentedSeq()
        parent[key] = value
    return value


def _at(seq: list, i: int, what: str) -> Any:
    if i < 0 or i >= len(seq):
        raise NotFoundError(f"{what} {i} introuvable")
    return seq[i]


def _categories(doc, ci: int) -> CommentedSeq:
    col = _at(_seq(doc, "columns"), ci, "Colonne")
    if not isinstance(col, dict):
        col = CommentedMap(categories=CommentedSeq())
        doc["columns"][ci] = col
    return _seq(col, "categories")


def _links(doc, ci: int, ki: int) -> CommentedSeq:
    return _seq(_at(_categories(doc, ci), ki, "Catégorie"), "links")


def _set_columns(doc, n: int) -> bool:
    """Ajuste le nombre de colonnes. Réduction refusée si une colonne retirée contient des catégories."""
    cols = _seq(doc, "columns")
    if len(cols) == n:
        return False
    if len(cols) < n:
        while len(cols) < n:
            cols.append(CommentedMap(categories=CommentedSeq()))
        return True
    busy = [str(i + 1) for i in range(n, len(cols))
            if isinstance(cols[i], dict) and (cols[i].get("categories") or [])]
    if busy:
        raise ConflictError(
            f"Impossible de passer à {n} colonne(s) : la/les colonne(s) {', '.join(busy)} "
            f"contiennent encore des catégories. Déplacez-les ou supprimez-les d'abord.")
    del cols[n:]
    return True


def _apply_link(target: dict, link: dict) -> None:
    target["name"] = link["name"]
    target["url"] = link["url"]
    if link.get("description"):
        target["description"] = link["description"]
    else:
        target.pop("description", None)
    if link.get("hidden"):
        target["hidden"] = True
    else:
        target.pop("hidden", None)
    style = {k: v for k, v in (link.get("style") or {}).items() if v is not None and v != ""}
    if style:
        target["style"] = CommentedMap(style)
    else:
        target.pop("style", None)


# ------------------------------------------------------------------ conversion

def _plain_link(l: dict) -> dict:
    style = l.get("style")
    return {
        "name": str(l.get("name") or ""),
        "url": str(l.get("url") or ""),
        "description": str(l.get("description") or ""),
        "hidden": bool(l.get("hidden")),
        "style": {str(k): v for k, v in style.items()} if isinstance(style, dict) else {},
    }


def to_plain(doc: dict) -> dict:
    return {
        "columns": [
            {"categories": [
                {"name": str(c.get("name") or ""),
                 "links": [_plain_link(l) for l in (c.get("links") or []) if isinstance(l, dict)]}
                for c in ((col if isinstance(col, dict) else {}).get("categories") or []) if isinstance(c, dict)
            ]}
            for col in (doc.get("columns") or [])
        ],
    }


# ------------------------------------------------------------------ API publique : données

def get_data() -> dict:
    with _lock:
        return to_plain(_read_data())


def _mutate(fn: Callable[[CommentedMap], None]) -> dict:
    with _lock:
        doc = _read_data()
        fn(doc)
        _write(DATA_FILE, doc)
        return to_plain(doc)


def add_category(ci: int, name: str) -> dict:
    def fn(doc):
        _categories(doc, ci).append(CommentedMap(name=name, links=CommentedSeq()))
    return _mutate(fn)


def rename_category(ci: int, ki: int, name: str) -> dict:
    def fn(doc):
        _at(_categories(doc, ci), ki, "Catégorie")["name"] = name
    return _mutate(fn)


def delete_category(ci: int, ki: int) -> dict:
    def fn(doc):
        cats = _categories(doc, ci)
        _at(cats, ki, "Catégorie")
        del cats[ki]
    return _mutate(fn)


def add_link(ci: int, ki: int, link: dict) -> dict:
    def fn(doc):
        new = CommentedMap()
        _apply_link(new, link)
        _links(doc, ci, ki).append(new)
    return _mutate(fn)


def update_link(ci: int, ki: int, li: int, link: dict) -> dict:
    def fn(doc):
        _apply_link(_at(_links(doc, ci, ki), li, "Lien"), link)
    return _mutate(fn)


def delete_link(ci: int, ki: int, li: int) -> dict:
    def fn(doc):
        links = _links(doc, ci, ki)
        _at(links, li, "Lien")
        del links[li]
    return _mutate(fn)


def move_link(src: dict, dst: dict) -> dict:
    def fn(doc):
        src_links = _links(doc, src["ci"], src["ki"])
        _at(src_links, src["li"], "Lien")
        dst_links = _links(doc, dst["ci"], dst["ki"])  # valide la cible avant de retirer
        link = src_links.pop(src["li"])
        index = dst["index"]
        if (src["ci"], src["ki"]) == (dst["ci"], dst["ki"]) and src["li"] < index:
            index -= 1
        dst_links.insert(max(0, min(index, len(dst_links))), link)
    return _mutate(fn)


def move_category(src: dict, dst: dict) -> dict:
    def fn(doc):
        src_cats = _categories(doc, src["ci"])
        _at(src_cats, src["ki"], "Catégorie")
        dst_cats = _categories(doc, dst["ci"])  # valide la cible avant de retirer
        cat = src_cats.pop(src["ki"])
        index = dst["index"]
        if src["ci"] == dst["ci"] and src["ki"] < index:
            index -= 1
        dst_cats.insert(max(0, min(index, len(dst_cats))), cat)
    return _mutate(fn)


# ------------------------------------------------------------------ API publique : thème

def get_theme() -> dict:
    """Thème validé ; `columns` reflète toujours le nombre réel de colonnes de data.yaml."""
    with _lock:
        theme = _theme_from_doc(_read_theme_doc())
        n = len(_seq(_read_data(), "columns"))
        if 1 <= n <= 6:
            theme["columns"] = n
        return theme


def save_theme(theme: dict) -> dict:
    with _lock:
        data_doc = _read_data()
        if _set_columns(data_doc, theme["columns"]):
            _write(DATA_FILE, data_doc)
        theme_doc = _read_theme_doc()
        _merge(theme_doc, theme)
        _write(THEME_FILE, theme_doc)
        return {"theme": _theme_from_doc(theme_doc), "data": to_plain(data_doc)}


def list_backgrounds() -> list[str]:
    if not FONDS_DIR.is_dir():
        return []
    return sorted((f.name for f in FONDS_DIR.iterdir()
                   if f.is_file() and f.suffix.lower() in IMAGE_EXT and not f.name.startswith(".")),
                  key=str.lower)

