# Watch Scraper

Simple API to scrape watch price information from Chrono24 and store it in a local MongoDB database running on the default port (27017).

## Endpoints

* `POST /scrape?query=<keyword>` - Scrape Chrono24 for the given keyword and store watch names and prices.
* `GET /watches` - List watches stored in the database.

## Running

Install dependencies from `requirements.txt`, ensure a MongoDB instance is running locally on port 27017, and run the API with a WSGI server such as `uvicorn`:

```bash
pip install -r requirements.txt
uvicorn api:app --reload
```

## Tests

Tests rely on mocked HTTP responses and an in-memory MongoDB stub. Execute them with:

```bash
pytest
```
