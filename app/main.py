"""Point d'entrée FastAPI : API REST + fichiers statiques."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import storage
from .favicon import FaviconCache
from .models import CategoryIn, CategoryMoveIn, LinkIn, MoveIn, Theme

STATIC_DIR = Path(__file__).resolve().parent / "static"

favicons = FaviconCache(storage.CACHE_DIR)


@asynccontextmanager
async def lifespan(_: FastAPI):
    storage.init()
    yield


app = FastAPI(title="FavoritePage", docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json", lifespan=lifespan)


@app.exception_handler(storage.NotFoundError)
async def _not_found(_: Request, exc: storage.NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(storage.ConflictError)
async def _conflict(_: Request, exc: storage.ConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(storage.StorageError)
async def _storage_error(_: Request, exc: storage.StorageError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/data")
def get_data():
    return storage.get_data()


# ----------------------------------------------------------------- catégories

@app.post("/api/columns/{ci}/categories")
def add_category(ci: int, body: CategoryIn):
    return storage.add_category(ci, body.name)


@app.put("/api/columns/{ci}/categories/{ki}")
def rename_category(ci: int, ki: int, body: CategoryIn):
    return storage.rename_category(ci, ki, body.name)


@app.delete("/api/columns/{ci}/categories/{ki}")
def delete_category(ci: int, ki: int):
    return storage.delete_category(ci, ki)


@app.post("/api/categories/move")
def move_category(body: CategoryMoveIn):
    return storage.move_category(body.source.model_dump(), body.target.model_dump())


# ---------------------------------------------------------------------- liens

@app.post("/api/columns/{ci}/categories/{ki}/links")
def add_link(ci: int, ki: int, body: LinkIn):
    return storage.add_link(ci, ki, body.model_dump())


@app.put("/api/columns/{ci}/categories/{ki}/links/{li}")
def update_link(ci: int, ki: int, li: int, body: LinkIn):
    return storage.update_link(ci, ki, li, body.model_dump())


@app.delete("/api/columns/{ci}/categories/{ki}/links/{li}")
def delete_link(ci: int, ki: int, li: int):
    return storage.delete_link(ci, ki, li)


@app.post("/api/links/move")
def move_link(body: MoveIn):
    return storage.move_link(body.source.model_dump(), body.target.model_dump())


# ---------------------------------------------------------------------- thème

@app.get("/api/theme")
def get_theme():
    return storage.get_theme()


@app.put("/api/theme")
def save_theme(body: Theme):
    return storage.save_theme(body.model_dump())


@app.get("/api/backgrounds")
def list_backgrounds():
    return storage.list_backgrounds()


@app.get("/api/favicon")
def favicon(url: str):
    res = favicons.get(url)
    if not res:
        raise HTTPException(status_code=404, detail="Favicon introuvable")
    path, media = res
    return FileResponse(path, media_type=media, headers={
        "Cache-Control": "public, max-age=86400",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    })


# Fichiers utilisateur (config/fonds, config/icons) puis frontend, montés en dernier
app.mount("/fonds", StaticFiles(directory=storage.FONDS_DIR, check_dir=False), name="fonds")
app.mount("/icons", StaticFiles(directory=storage.ICONS_DIR, check_dir=False), name="icons")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

