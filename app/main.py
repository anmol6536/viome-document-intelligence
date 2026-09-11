from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.extractions import router as extractions_router

app = FastAPI(title="Viome Document Intelligence")

# Demo-only: lets a browser-hosted demo page (e.g. the gateway repo's
# presentation/index.html) call this API directly, cross-origin. No
# cookies/session auth to leak - real auth is per-request headers, checked
# server-side same as always.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(extractions_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
