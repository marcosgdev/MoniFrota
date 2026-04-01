"""
Ponto de entrada da aplicação FrotaGov.
Execute com:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import secrets
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.api import router as api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="America/Belem")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    if not settings.use_mock:
        from app.db.database import init_db
        from app.services.ingestion_service import sync_hoje, sync_ontem

        await init_db()
        logger.info("Banco inicializado.")

        # Sincroniza ontem + hoje imediatamente ao subir
        await sync_ontem()
        await sync_hoje()

        # Scheduler: sync_hoje a cada N minutos durante o dia
        scheduler.add_job(
            sync_hoje,
            "interval",
            minutes=settings.sync_interval_min,
            id="sync_hoje",
        )
        # Scheduler: sync_ontem toda meia-noite (captura registros tardios)
        scheduler.add_job(
            sync_ontem,
            "cron",
            hour=0,
            minute=5,
            id="sync_ontem",
        )
        scheduler.start()
        logger.info(f"Scheduler iniciado — sync a cada {settings.sync_interval_min} min.")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    if scheduler.running:
        scheduler.shutdown(wait=False)

    if not settings.use_mock:
        from app.db.database import close_db
        await close_db()


app = FastAPI(
    title="FrotaGov API",
    description="Monitoramento de abastecimentos da frota pública",
    version="2.0.0",
    docs_url="/docs" if settings.env == "development" else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.env == "development" else [],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# --- Autenticação básica (substitua por JWT em produção) ---
security = HTTPBasic()


def autenticar(credentials: HTTPBasicCredentials = Depends(security)):
    user_ok = secrets.compare_digest(credentials.username, settings.dashboard_user)
    pass_ok = secrets.compare_digest(credentials.password, settings.dashboard_pass)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# --- Rotas da API (protegidas) ---
app.include_router(api_router, dependencies=[Depends(autenticar)])

# --- Frontend estático ---
STATIC_DIR = Path(__file__).parent.parent / "frontend"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", dependencies=[Depends(autenticar)])
    async def serve_frontend():
        return FileResponse(str(STATIC_DIR / "index.html"))
