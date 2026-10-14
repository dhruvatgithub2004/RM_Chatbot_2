"""Local exact and semantic response cache for co-pilot chat."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any

from . import config

log = logging.getLogger("rm_copilot.cache")
CACHE_VERSION = "chat-response-v1"


class ChatResponseCache:
    def __init__(self, *, client=None, embedding_function=None):
        self._client = client
        self._embedding_function = embedding_function
        self._collection = None
        self._lock = threading.RLock()
        self._embedding_ready = threading.Event()
        self._memory: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._pending: list[tuple[str, str, str, str, str, float]] = []
        self._warmup_running = False
        self._warmup_retry_at = 0.0
        self._disabled = False
        self._warned = False
        self._writes = 0

    @staticmethod
    def exact_key(system: str, messages: list[dict], model: str) -> str:
        payload = json.dumps({
            "version": CACHE_VERSION,
            "system": system,
            "messages": messages,
            "provider": config.LLM_PROVIDER,
            "model": model,
            "max_tokens": config.LLM_MAX_TOKENS,
            "num_ctx": config.OLLAMA_NUM_CTX if config.LLM_PROVIDER == "ollama" else None,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def semantic_namespace(system: str, model: str) -> str:
        payload = f"{CACHE_VERSION}\0{config.LLM_PROVIDER}\0{model}\0{config.LLM_MAX_TOKENS}\0{config.OLLAMA_NUM_CTX}\0{config.CHAT_CACHE_SEMANTIC_DISTANCE}\0{system}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _collection_or_none(self):
        if not config.CHAT_CACHE_ENABLED or self._disabled:
            return None
        with self._lock:
            if self._collection is not None:
                return self._collection
            try:
                if self._client is None:
                    import chromadb

                    self._client = chromadb.PersistentClient(path=str(config.CHAT_CACHE_PATH))
                options: dict[str, Any] = {"metadata": {"hnsw:space": "cosine"}}
                if self._embedding_function is not None:
                    options["embedding_function"] = self._embedding_function
                self._collection = self._client.get_or_create_collection("chat_responses", **options)
                return self._collection
            except Exception as exc:  # noqa: BLE001 - cache failure must never break chat
                self._disable(exc)
                return None

    def warm_up(self) -> None:
        """Download/initialize Chroma's local embedding model off the request path."""
        with self._lock:
            if self._disabled or self._embedding_ready.is_set() or self._warmup_running:
                return
            self._warmup_running = True
            self._warmup_retry_at = time.time() + 60
        collection = self._collection_or_none()
        if collection is None:
            with self._lock:
                self._warmup_running = False
            return
        warm_id = f"warmup-{uuid.uuid4().hex}"
        try:
            collection.upsert(
                ids=[warm_id],
                documents=["semantic cache warmup"],
                metadatas=[{"namespace": "__warmup__", "model": "__warmup__", "expires_at": time.time()}],
            )
            collection.delete(ids=[warm_id])
            self._embedding_ready.set()
            with self._lock:
                pending = self._pending
                self._pending = []
            for entry in pending:
                self._persist(*entry)
        except Exception as exc:  # noqa: BLE001 - exact cache remains available
            self._warn(exc)
        finally:
            with self._lock:
                self._warmup_running = False

    def get_exact(self, key: str) -> str | None:
        if not config.CHAT_CACHE_ENABLED:
            return None
        now = time.time()
        with self._lock:
            entry = self._memory.get(key)
            if entry:
                expires_at, response = entry
                if expires_at > now:
                    self._memory.move_to_end(key)
                    return response
                del self._memory[key]

        collection = self._collection_or_none()
        if collection is None:
            return None
        try:
            result = collection.get(ids=[key], include=["metadatas"])
            metadata = (result.get("metadatas") or [None])[0]
            if not metadata:
                return None
            if float(metadata.get("expires_at", 0)) <= now:
                collection.delete(ids=[key])
                return None
            response = metadata.get("response")
            if isinstance(response, str):
                self._remember(key, float(metadata["expires_at"]), response)
                return response
        except Exception as exc:  # noqa: BLE001
            self._warn(exc)
        return None

    def get_semantic(self, question: str, namespace: str, model: str) -> str | None:
        if not config.CHAT_CACHE_ENABLED or not question.strip():
            return None
        if not self._embedding_ready.is_set():
            with self._lock:
                should_retry = not self._disabled and not self._warmup_running and time.time() >= self._warmup_retry_at
            if should_retry:
                threading.Thread(target=self.warm_up, name="chat-cache-warmup-retry", daemon=True).start()
            return None
        collection = self._collection_or_none()
        if collection is None:
            return None
        try:
            if collection.count() == 0:
                return None
            result = collection.query(
                query_texts=[question],
                n_results=1,
                where={"$and": [{"namespace": namespace}, {"model": model}]},
                include=["metadatas", "distances"],
            )
            ids = result.get("ids", [[]])[0]
            distances = result.get("distances", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            if not ids or not distances or not metadatas or distances[0] > config.CHAT_CACHE_SEMANTIC_DISTANCE:
                return None
            metadata = metadatas[0]
            if float(metadata.get("expires_at", 0)) <= time.time():
                collection.delete(ids=[ids[0]])
                return None
            response = metadata.get("response")
            if isinstance(response, str):
                return response
        except Exception as exc:  # noqa: BLE001 - semantic cache is optional
            self._warn(exc)
        return None

    def store(self, key: str, namespace: str, model: str, question: str, response: str) -> None:
        if not config.CHAT_CACHE_ENABLED:
            return
        expires_at = time.time() + config.CHAT_CACHE_TTL_SECONDS
        self._remember(key, expires_at, response)
        if not self._embedding_ready.is_set():
            with self._lock:
                if not self._embedding_ready.is_set():
                    self._pending.append((key, namespace, model, question, response, expires_at))
                    if len(self._pending) > config.CHAT_CACHE_MAX_ENTRIES:
                        self._pending.pop(0)
                    return
        self._persist(key, namespace, model, question, response, expires_at)

    def _persist(self, key: str, namespace: str, model: str, question: str, response: str, expires_at: float) -> None:
        collection = self._collection_or_none()
        if collection is None:
            return
        try:
            collection.upsert(
                ids=[key],
                documents=[question],
                metadatas=[{
                    "namespace": namespace,
                    "model": model,
                    "response": response,
                    "created_at": time.time(),
                    "expires_at": expires_at,
                }],
            )
            self._writes += 1
            if self._writes % 25 == 0:
                self._prune(collection)
        except Exception as exc:  # noqa: BLE001
            self._warn(exc)

    def _remember(self, key: str, expires_at: float, response: str) -> None:
        with self._lock:
            self._memory[key] = (expires_at, response)
            self._memory.move_to_end(key)
            while len(self._memory) > min(config.CHAT_CACHE_MAX_ENTRIES, 256):
                self._memory.popitem(last=False)

    def _prune(self, collection) -> None:
        result = collection.get(include=["metadatas"])
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        now = time.time()
        expired = [entry_id for entry_id, metadata in zip(ids, metadatas)
                   if float(metadata.get("expires_at", 0)) <= now]
        if expired:
            collection.delete(ids=expired)
        remaining = [(entry_id, metadata) for entry_id, metadata in zip(ids, metadatas) if entry_id not in expired]
        overflow = len(remaining) - config.CHAT_CACHE_MAX_ENTRIES
        if overflow > 0:
            oldest = sorted(remaining, key=lambda item: float(item[1].get("created_at", 0)))[:overflow]
            collection.delete(ids=[entry_id for entry_id, _ in oldest])

    def _disable(self, exc: Exception) -> None:
        self._disabled = True
        self._warn(exc)

    def _warn(self, exc: Exception) -> None:
        if not self._warned:
            log.warning("Chroma chat cache unavailable; continuing without vector cache: %s", exc)
            self._warned = True


chat_cache = ChatResponseCache()