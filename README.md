# Watch Scraper

Simple API to scrape watch price information from Chrono24 and store it in a SQLite database.

## Endpoints

* `POST /scrape?query=<keyword>` - Scrape Chrono24 for the given keyword and store watch names and prices.
* `GET /watches` - List watches stored in the database.

## Running

Install dependencies from `requirements.txt` and run the API with a WSGI server such as `uvicorn`:

```bash
pip install -r requirements.txt
uvicorn api:app --reload
```

## Tests

Tests rely on mocked HTTP responses and a temporary SQLite database. Execute them with:

```bash
pytest
```
