from fastapi import FastAPI

app = FastAPI(title="Viome Document Intelligence")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
