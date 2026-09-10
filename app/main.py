from fastapi import FastAPI

from app.api.extractions import router as extractions_router

app = FastAPI(title="Viome Document Intelligence")
app.include_router(extractions_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
