from fastapi import FastAPI


app = FastAPI(
    title="Agente Clínicas",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "database": "healthy",
    }