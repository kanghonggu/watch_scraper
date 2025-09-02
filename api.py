from fastapi import FastAPI, HTTPException
from requests import HTTPError
from scraper import fetch_watch_prices
from database import init_db, insert_watches, get_watches

app = FastAPI()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.post("/scrape")
def scrape(query: str, source: str = "chrono24"):
    try:
        watches = fetch_watch_prices(query, source)
    except HTTPError as exc:
        status = exc.response.status_code if exc.response else 502
        if status == 403:
            detail = f"{source}에서 접근이 거부되었습니다. 잠시 후 다시 시도하세요."
        else:
            detail = f"{source}에서 데이터를 가져오지 못했습니다: {exc}"
        raise HTTPException(status_code=status, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not watches:
        raise HTTPException(status_code=404, detail="No watches found")
    inserted = insert_watches(watches)
    return {"count": inserted}


@app.get("/watches")
def list_watches():
    return get_watches()
