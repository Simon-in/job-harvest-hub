from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import BASE_DIR
from app.database import init_db

app = FastAPI(title="job-harvest-hub", version="0.2.0")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(router)
web_dir = BASE_DIR / "app" / "web"
app.mount("/web", StaticFiles(directory=str(web_dir)), name="web")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(web_dir / "index.html")
