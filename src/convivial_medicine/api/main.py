from __future__ import annotations

from fastapi import FastAPI

from convivial_medicine import __version__

app = FastAPI(
    title="Convivial Medicine Corpus Constructor",
    version=__version__,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "convivial-medicine", "status": "ok"}
