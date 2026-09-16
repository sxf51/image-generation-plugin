"""Plugin-owned task history, assets and caches on top of the host storage service.

The host hands this plugin a storage object through its runtime context. That object
already knows which directory and which key namespace belong to this plugin, so
nothing here builds a connection, resolves a host path, or invents a key prefix.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import redis


class StorageUnavailable(redis.ConnectionError):
    """Raised when the host storage service has no usable backend right now."""


# 中文: 前端认得的失败码。工具返回的 error_code 只有落在这个集合里才会被存下来,
# 其余一律归到 task_failed——既避免把服务商原始报错(可能含服务端路径/密钥片段)
# 透出去, 也避免前端拿到没有对应译文的码而显示成裸标识符。
FAILURE_CODES = frozenset(
    {
        "missing_api_key",
        "missing_prompt",
        "missing_source_image",
        "source_image_unavailable",
        "mask_unavailable",
        "provider_edit_unsupported",
        "provider_unauthorized",
        "provider_rate_limited",
        "provider_rejected",
        "provider_timeout",
        "provider_unreachable",
        "provider_failed",
    }
)


def _failure_code(result):
    code = str(result.get("error_code") or "").strip()
    return code if code in FAILURE_CODES else "task_failed"


class Store:
    def __init__(self, storage):
        if storage is None:
            raise StorageUnavailable("the host did not provide a storage service")
        self.storage = storage
        self.root = storage.dir("images")
        client = storage.client()
        if client is None:
            raise StorageUnavailable("the storage service has no usable backend")
        self.redis = client

    def key(self, *parts):
        return self.storage.key(*parts)

    def owner_key(self, owner, suffix):
        return self.storage.key("owner", hashlib.sha256(str(owner).encode()).hexdigest(), suffix)

    def create(self, owner, mode, payload, status="running", max_pending=None):
        task_id = uuid.uuid4().hex
        now = time.time()
        item = {
            "id": task_id,
            "owner": owner,
            "created": now,
            "finished": None,
            "status": status,
            "mode": mode,
            "prompt": str(payload.get("prompt") or payload.get("query") or ""),
            "size": str(payload.get("size") or "1024x1024"),
            "image_count": int(payload.get("image_count") or 1),
            "parent_id": payload.get("parent_id"),
            "reference": payload.get("reference"),
            "template_id": payload.get("template_id"),
            "source": None,
            "model": None,
            "trace_id": None,
            "error": None,
            "images": [],
        }
        owner_pending = self.owner_key(owner, "pending")
        while True:
            with self.redis.pipeline() as pipe:
                try:
                    pipe.watch(owner_pending)
                    if max_pending is not None and pipe.zcard(owner_pending) >= max_pending:
                        return None
                    pipe.multi()
                    pipe.hset(self.key("tasks"), task_id, json.dumps(item, ensure_ascii=False))
                    pipe.zadd(self.key("timeline"), {task_id: now})
                    pipe.zadd(self.owner_key(owner, "timeline"), {task_id: now})
                    pipe.zadd(self.key("pending"), {task_id: now})
                    pipe.zadd(owner_pending, {task_id: now})
                    pipe.execute()
                    return task_id
                except redis.WatchError:
                    continue

    def get(self, task_id, owner):
        raw = self.redis.hget(self.key("tasks"), task_id)
        item = json.loads(raw) if raw else None
        return self.public(item) if item and item["owner"] == owner else None

    def public(self, item):
        result = dict(item)
        result.pop("owner", None)
        result["images"] = [{**image, "available": self.resolve(image["name"]) is not None} for image in item["images"]]
        return result

    def resolve(self, name):
        if not name or "/" in name or "\\" in name or "\x00" in name:
            return None
        path = (self.root / name).resolve()
        return path if path.is_relative_to(self.root) and path.is_file() else None

    def asset(self, asset_id, owner):
        raw = self.redis.hget(self.key("assets"), asset_id)
        item = json.loads(raw) if raw else None
        return item if item and item["owner"] == owner and self.resolve(item["name"]) else None

    def add_asset(self, owner, name, kind, task_id=None):
        item = {
            "id": uuid.uuid4().hex,
            "owner": owner,
            "name": name,
            "kind": kind,
            "task_id": task_id,
            "created": time.time(),
        }
        with self.redis.pipeline() as pipe:
            pipe.hset(self.key("assets"), item["id"], json.dumps(item))
            pipe.zadd(self.owner_key(owner, "assets:" + kind), {item["id"]: item["created"]})
            pipe.execute()
        return {k: v for k, v in item.items() if k not in ("owner", "created")}

    def finish(self, task_id, owner, result, status=None):
        assets = []
        for raw in result.get("images", []):
            path = Path(raw).resolve()
            if path.parent == self.root and path.is_file():
                assets.append({"id": uuid.uuid4().hex, "name": path.name, "kind": "output", "task_id": task_id})
        while True:
            with self.redis.pipeline() as pipe:
                try:
                    pipe.watch(self.key("tasks"))
                    raw = pipe.hget(self.key("tasks"), task_id)
                    item = json.loads(raw) if raw else None
                    if not item or item["owner"] != owner or item["status"] not in ("queued", "running"):
                        return
                    final_status = status or ("success" if result.get("status") == "success" else "error")
                    item.update(
                        status=final_status,
                        finished=time.time(),
                        source=result.get("source", "provider"),
                        model=result.get("model"),
                        trace_id=result.get("trace_id"),
                        images=assets,
                        # A message code, never a sentence: the studio page and the chat
                        # client render it in the reader's own language. Only codes from
                        # the known set are stored, so a raw provider message (which can
                        # carry a server path or a key fragment) never reaches the page.
                        error=None if final_status == "success" else _failure_code(result),
                    )
                    pipe.multi()
                    pipe.hset(self.key("tasks"), task_id, json.dumps(item, ensure_ascii=False))
                    pipe.zrem(self.key("pending"), task_id)
                    pipe.zrem(self.owner_key(owner, "pending"), task_id)
                    for asset in assets:
                        pipe.hset(self.key("assets"), asset["id"], json.dumps({**asset, "owner": owner}))
                        pipe.zadd(self.owner_key(owner, "assets:output"), {asset["id"]: item["finished"]})
                    pipe.execute()
                    return
                except redis.WatchError:
                    continue

    def _tasks(self, ids):
        if not ids:
            return []
        return [json.loads(raw) for raw in self.redis.hmget(self.key("tasks"), ids) if raw]

    def history(self, owner, page=1, status="", search=""):
        ids = self.redis.zrevrange(self.owner_key(owner, "timeline"), 0, -1)
        rows = [
            row
            for row in self._tasks(ids)
            if (not status or row["status"] == status) and (not search or search.casefold() in row["prompt"].casefold())
        ]
        return {
            "items": [self.public(row) for row in rows[(page - 1) * 20 : page * 20]],
            "total": len(rows),
            "page": page,
            "page_size": 20,
        }

    def gallery(self, owner, limit=60):
        ids = self.redis.zrevrange(self.owner_key(owner, "assets:output"), 0, -1)
        rows = [json.loads(raw) for raw in self.redis.hmget(self.key("assets"), ids) if raw] if ids else []
        items, seen = [], set()
        for row in rows:
            path = self.resolve(row["name"])
            if path and row["name"] not in seen:
                try:
                    stat = path.stat()
                except OSError:
                    continue
                seen.add(row["name"])
                item = {k: v for k, v in row.items() if k not in ("owner", "created")}
                items.append({**item, "size": stat.st_size, "modified": int(stat.st_mtime)})
                if len(items) >= limit:
                    break
        return items

    def expire(self, timeout):
        ids = self.redis.zrangebyscore(self.key("pending"), "-inf", time.time() - timeout)
        for row in self._tasks(ids):
            self.finish(row["id"], row["owner"], {"status": "error"}, status="interrupted")

    def stats(self, days=30):
        today = datetime.now(UTC).date()
        start = today - timedelta(days=days - 1)
        since = datetime.combine(start, datetime.min.time(), tzinfo=UTC).timestamp()
        until = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=UTC).timestamp() - 0.001
        rows = self._tasks(self.redis.zrangebyscore(self.key("timeline"), since, until))
        series = {
            str(start + timedelta(days=i)): {
                "date": str(start + timedelta(days=i)),
                "uses": 0,
                "active_users": 0,
                "success": 0,
                "failed": 0,
            }
            for i in range(days)
        }
        users = {day: set() for day in series}
        for row in rows:
            day = str(datetime.fromtimestamp(row["created"], UTC).date())
            series[day]["uses"] += 1
            if row["owner"] != "unknown":
                users[day].add(row["owner"])
            series[day]["success"] += row["status"] == "success"
            series[day]["failed"] += row["status"] in ("error", "interrupted")
        for day, bucket in series.items():
            bucket["active_users"] = len(users[day])
        return {
            "total_tasks": self.redis.zcard(self.key("timeline")),
            "uses": len(rows),
            "active_users": len(set().union(*users.values())),
            "success": sum(r["status"] == "success" for r in rows),
            "failed": sum(r["status"] in ("error", "interrupted") for r in rows),
            "cache_hits": sum(r["source"] == "cache" for r in rows),
            "output_images": sum(len(r["images"]) for r in rows if r["source"] != "cache"),
            "edits": sum(r["mode"] == "edit" for r in rows),
            "days": days,
            "timezone": "UTC",
            "series": list(series.values()),
        }

    def cache_key(self, **options):
        return self.key("cache", hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest())

    def cache_get(self, **options):
        key = self.cache_key(**options)
        raw = self.redis.get(key)
        paths = json.loads(raw) if raw else None
        if paths and not all(Path(path).is_file() for path in paths):
            self.redis.delete(key)
            return None
        return paths

    def cache_set(self, *, paths, ttl_seconds, **options):
        self.redis.set(self.cache_key(**options), json.dumps(paths), ex=max(1, int(ttl_seconds)))
