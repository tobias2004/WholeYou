from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import FRONTEND_BASE_URL
from data_sources.ai.routes import router as ai_router
from data_sources.clinical.routes import router as clinical_router
from data_sources.local_ai.routes import router as local_ai_context_router
from data_sources.wearables.routes import router as wearables_router
from integrations.epic.routes import router as epic_router
from logs.routes import router as logs_router

app = FastAPI(title="WholeYou")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_BASE_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(epic_router)
app.include_router(clinical_router)
app.include_router(wearables_router)
app.include_router(local_ai_context_router)
app.include_router(ai_router)
app.include_router(logs_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": "WholeYou"}
