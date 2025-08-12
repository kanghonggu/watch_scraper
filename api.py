from fastapi import FastAPI, HTTPException
from scraper import fetch_watch_prices
from database import init_db, insert_watches, get_watches

app = FastAPI()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.post("/scrape")
def scrape(query: str, source: str = "chrono24"):
    watches = fetch_watch_prices(query, source)
    if not watches:
        raise HTTPException(status_code=404, detail="No watches found")
    inserted = insert_watches(watches)
    return {"count": inserted}


@app.get("/watches")
def list_watches():
    return get_watches()
