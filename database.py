"""Database helpers using MongoDB."""

from typing import List, Dict

from pymongo import MongoClient

DB_NAME = "watchdb"
COLLECTION_NAME = "watches"

client: MongoClient | None = None


def init_db() -> None:
    """Initialize the MongoDB connection and ensure indexes exist."""
    global client
    if client is None:
        # Connect to a local MongoDB instance on the default port (27017)
        client = MongoClient("mongodb://localhost:27017")
    client[DB_NAME][COLLECTION_NAME].create_index("name")


def _get_collection():
    if client is None:
        init_db()
    return client[DB_NAME][COLLECTION_NAME]


def insert_watches(watches: List[Dict[str, str]]) -> int:
    """Insert a list of watches into MongoDB."""
    if not watches:
        return 0
    result = _get_collection().insert_many(watches)
    return len(result.inserted_ids)


def get_watches() -> List[Dict[str, str]]:
    """Retrieve all stored watches."""
    cursor = _get_collection().find()
    result: List[Dict[str, str]] = []
    for doc in cursor:
        doc = {k: v for k, v in doc.items() if k != "_id"}
        result.append(doc)
    return result

