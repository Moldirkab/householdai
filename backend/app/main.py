import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .api import router
from .db import Base, SessionLocal, engine, migrate
from .forecast import national_seasonal_index
from .models import User

app = FastAPI(title="HouseholdAI: shared household budget with AI forecasts")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(engine)
    migrate()
    if config.SEED_DEMO_ON_START:
        db = SessionLocal()
        try:
            empty = db.query(User).count() == 0
        finally:
            db.close()
        if empty:
            from .seed import seed
            seed(1)
    # fit the national SARIMA models in the background so the first forecast is fast
    threading.Thread(target=national_seasonal_index, daemon=True).start()


if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = config.FRONTEND_DIST / path
        return FileResponse(f if path and f.is_file() else config.FRONTEND_DIST / "index.html")
