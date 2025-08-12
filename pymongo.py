"""Minimal stub of pymongo for environments without MongoDB."""

from typing import Any, Dict, Iterable, List


class _Result:
    def __init__(self, count: int) -> None:
        self.inserted_ids = list(range(count))


class Collection:
    def __init__(self) -> None:
        self._data: List[Dict[str, Any]] = []

    def insert_many(self, docs: Iterable[Dict[str, Any]]):
        docs_list = list(docs)
        self._data.extend(docs_list)
        return _Result(len(docs_list))

    def find(self, filter=None, projection=None):
        for doc in self._data:
            if projection:
                yield {k: doc.get(k) for k in projection if k != "_id"}
            else:
                yield doc

    def create_index(self, *args, **kwargs):
        return None


class Database:
    def __init__(self) -> None:
        self._collections: Dict[str, Collection] = {}

    def __getitem__(self, name: str) -> Collection:
        return self._collections.setdefault(name, Collection())


class MongoClient:
    def __init__(self, *args, **kwargs) -> None:
        self._databases: Dict[str, Database] = {}

    def __getitem__(self, name: str) -> Database:
        return self._databases.setdefault(name, Database())

