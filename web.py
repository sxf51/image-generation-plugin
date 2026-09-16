"""Image studio endpoints, served exclusively through the host's authenticated bridge.

Every failure is reported as a stable snake_case message code, never as a sentence.
Users of this deployment do not share one language, so the page turns the code into
text in whichever language the reader is using.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import importlib.util
import io
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from extension.plugin_web import bytes_response, error_response, json_response
from PIL import Image, UnidentifiedImageError
from redis.exceptions import RedisError

_spec = importlib.util.spec_from_file_location("image_studio_web_store", Path(__file__).with_name("studio.py"))
_studio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_studio)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_PROMPT = 12000
MAX_IMAGES = 4
MAX_PENDING = 3
logger = logging.getLogger(__name__)
SIZES = ("1024x1024", "1536x1024", "1024x1536")


def register_web_apis(web: Any, plugin: Any, runtime_context: dict[str, Any]) -> None:  # noqa: PLR0915
    executor = runtime_context.get("tool_executor")
    # The host hands over a storage object already scoped to this plugin; the page
    # endpoints never name a directory or a key prefix of their own.
    storage = runtime_context.get("storage")
    pending = set()
    templates = json.loads(Path(__file__).with_name("templates.json").read_text(encoding="utf-8"))

    def store():
        return _studio.Store(storage)

    async def expire(ledger):
        timeout = float((plugin.config or {}).get("generation", {}).get("timeout_seconds", 180))
        await asyncio.to_thread(ledger.expire, max(600, timeout + 300))

    async def connectivity(request):
        _ = request
        config = plugin.config or {}
        source = str(config.get("model_source") or "custom")
        if source == "host_model":
            llm = runtime_context.get("llm_config")
            if llm is None or not getattr(llm, "base_url", "") or not getattr(llm, "api_key", ""):
                return error_response("host_model_unconfigured", 422)
            return {
                "status": "success",
                "source": source,
                "provider": getattr(llm, "provider_name", "") or getattr(llm, "provider", ""),
                "model": getattr(llm, "model", ""),
                "network_probe": False,
            }
        if source == "custom":
            provider = config.get("openai_images", {}) if isinstance(config.get("openai_images"), dict) else {}
            if not str(provider.get("api_base") or "").strip() or not str(provider.get("api_key") or "").strip():
                return error_response("custom_model_unconfigured", 422)
            return {
                "status": "success",
                "source": source,
                "provider": "openai_images",
                "model": str(provider.get("model") or ""),
                "network_probe": False,
            }
        return error_response("invalid_model_source", 422)
    async def template_list(request):
        return {"items": templates}

    async def stats(request):
        try:
            days = int(request.query.get("days", 30))
            if days not in (7, 30, 90):
                raise ValueError
        except (ValueError, TypeError):
            return error_response("invalid_days", 422)
        generation = (plugin.config or {}).get("generation", {})
        try:
            ledger = store()
        except _studio.StorageUnavailable:
            return {
                "status": "error",
                "message": "storage_unavailable",
                "count": 0,
                "provider": generation.get("provider", "openai_images"),
                "size": generation.get("size", SIZES[0]),
            }
        await expire(ledger)
        summary = await asyncio.to_thread(ledger.stats, days)
        images = await asyncio.to_thread(ledger.gallery, request.username, 200)
        return {
            **summary,
            "count": len(images),
            "bytes": sum(i["size"] for i in images),
            "provider": generation.get("provider", "openai_images"),
            "size": generation.get("size", SIZES[0]),
        }

    async def gallery(request):
        try:
            limit = max(1, min(200, int(request.query.get("limit", 60))))
        except (ValueError, TypeError):
            return error_response("invalid_limit", 422)
        return {"items": await asyncio.to_thread(store().gallery, request.username, limit)}

    async def recent(request):
        return [
            {"name": i["name"], "size_kb": round(i["size"] / 1024, 1), "modified": i["modified"]}
            for i in await asyncio.to_thread(store().gallery, request.username, 10)
        ]

    async def history(request):
        try:
            page = int(request.query.get("page", 1))
            if page < 1:
                raise ValueError
        except (ValueError, TypeError):
            return error_response("invalid_page", 422)
        ledger = store()
        await expire(ledger)
        task_id = request.query.get("id")
        if task_id:
            task = await asyncio.to_thread(ledger.get, task_id, request.username)
            return task if task else error_response("unknown_task", 404)
        return await asyncio.to_thread(
            ledger.history,
            request.username,
            page,
            request.query.get("status", ""),
            str(request.query.get("search", ""))[:200],
        )

    async def upload(request):
        body = await request.json(default={})
        if not isinstance(body, dict) or not isinstance(body.get("data"), str):
            return error_response("reference_required", 422)
        data = body["data"]
        if len(data) > (MAX_UPLOAD_BYTES * 4 // 3 + 256):
            return error_response("reference_too_large", 413)
        ledger = store()
        try:
            raw = base64.b64decode(data.split(",", 1)[-1], validate=True)
            if len(raw) > MAX_UPLOAD_BYTES:
                return error_response("reference_too_large", 413)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ("PNG", "JPEG", "WEBP") or source.width * source.height > MAX_PIXELS:
                    return error_response("reference_unsupported_format", 422)
                # Decode and re-encode: discard metadata and never trust filename or MIME from the browser.
                image = source.convert("RGBA")
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
            name = "reference-" + uuid.uuid4().hex + ".png"
            (ledger.root / name).write_bytes(buffer.getvalue())
            return json_response(await asyncio.to_thread(ledger.add_asset, request.username, name, "reference"), 201)
        except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError):
            return error_response("reference_invalid", 422)

    async def thumbnail(request):
        ledger = store()
        asset = await asyncio.to_thread(ledger.asset, str(request.query.get("id", "")), request.username)
        if not asset:
            return error_response("unknown_image", 404)
        try:
            with Image.open(ledger.resolve(asset["name"])) as source:
                preview = source.convert("RGB")
                preview.thumbnail((640, 640))
                buffer = io.BytesIO()
                preview.save(buffer, format="JPEG", quality=85)
            return bytes_response(buffer.getvalue(), "image/jpeg")
        except (OSError, ValueError, Image.DecompressionBombError):
            return error_response("image_unavailable", 404)

    async def validate(request):  # noqa: PLR0911
        body = await request.json(default={})
        if not isinstance(body, dict):
            return None, error_response("invalid_request", 422)
        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            return None, error_response("prompt_required", 422)
        if len(prompt) > MAX_PROMPT:
            return None, error_response("prompt_too_long", 422)
        try:
            count = int(body.get("image_count", 1))
            if isinstance(body.get("image_count"), bool) or str(count) != str(body.get("image_count", 1)):
                raise ValueError
            if not 1 <= count <= MAX_IMAGES or body.get("size", SIZES[0]) not in SIZES:
                raise ValueError
        except (ValueError, TypeError):
            return None, error_response("invalid_size_or_count", 422)
        payload = {
            "query": prompt,
            "prompt": prompt,
            "actor_id": request.username,
            "source": "plugin-page",
            "size": body.get("size", SIZES[0]),
            "image_count": count,
        }
        ledger = store()
        reference = body.get("reference")
        parent_id = body.get("parent_id")
        if reference:
            asset = await asyncio.to_thread(ledger.asset, str(reference), request.username)
            if not asset:
                return None, error_response("reference_missing", 404)
            payload.update(reference=reference, image_path=str(ledger.resolve(asset["name"])))
        if parent_id:
            parent = await asyncio.to_thread(ledger.get, str(parent_id), request.username)
            if not parent or not any(i["id"] == reference for i in parent["images"]):
                return None, error_response("reference_not_in_parent", 422)
            payload["parent_id"] = parent_id
        if body.get("template_id"):
            template = next((t for t in templates if t["id"] == body["template_id"]), None)
            if not template:
                return None, error_response("unknown_template", 422)
            if template.get("requires_reference") and not reference:
                return None, error_response("template_requires_reference", 422)
            payload["template_id"] = template["id"]
        return payload, None

    async def run(payload, task_id):
        ledger = store()
        mode = "edit" if payload.get("image_path") else "generate"
        try:
            timeout = max(1, float((plugin.config or {}).get("generation", {}).get("timeout_seconds", 180)))
            tool_name = "image_edit_tool" if mode == "edit" else "image_generate_tool"
            trace_id = f"plugin-page:{plugin.name}:{payload['actor_id']}:{task_id}"
            tool_payload = {**payload, "trace_id": trace_id}
            result = await asyncio.wait_for(
                executor.execute(
                    tool_name,
                    tool_payload,
                    trace_id=trace_id,
                    timeout_sec=timeout,
                ),
                timeout=timeout + 30,
            )
            if not isinstance(result, dict):
                result = {"status": "error"}
        except asyncio.CancelledError:
            await asyncio.to_thread(ledger.finish, task_id, payload["actor_id"], {"status": "error"})
            raise
        except Exception:
            logger.exception("Image studio task %s failed", task_id)
            result = {"status": "error"}
        await asyncio.to_thread(ledger.finish, task_id, payload["actor_id"], result)
        return result

    def completed(task):
        pending.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("Image studio background task could not persist its result", exc_info=task.exception())

    async def submit(request, background=True):
        if executor is None:
            return error_response("executor_unavailable", 503)
        payload, problem = await validate(request)
        if problem is not None:
            return problem
        ledger = store()
        await expire(ledger)
        mode = "edit" if payload.get("image_path") else "generate"
        task_id = await asyncio.to_thread(
            ledger.create, request.username, mode, payload, "queued", max_pending=MAX_PENDING
        )
        if task_id is None:
            return error_response("too_many_pending_tasks", 429)
        if background:
            task = asyncio.create_task(run(payload, task_id))
            pending.add(task)
            task.add_done_callback(completed)
            return json_response(await asyncio.to_thread(ledger.get, task_id, request.username), 202)
        result = await run(payload, task_id)
        public = {k: result[k] for k in ("status", "model", "source", "size", "image_count") if k in result}
        public["task"] = await asyncio.to_thread(ledger.get, task_id, request.username)
        public["items"] = await asyncio.to_thread(ledger.gallery, request.username)
        return json_response(public, 200 if result.get("status") == "success" else 422)

    async def generate(request):
        return await submit(request, background=False)

    def guarded(handler):
        async def call(request):
            try:
                return await handler(request)
            except RedisError:
                logger.exception("Image studio Redis storage unavailable")
                return error_response("storage_unavailable", 503)

        return call

    for endpoint, handler, methods, description in (
        ("templates", template_list, ["GET"], "Prompt templates"),
        ("connectivity", connectivity, ["POST"], "Validate the selected image model configuration"),
        ("stats", stats, ["GET"], "Usage statistics, UTC daily buckets"),
        ("gallery", gallery, ["GET"], "Current user output images"),
        ("recent", recent, ["GET"], "Recent outputs"),
        ("history", history, ["GET"], "Current user task history"),
        ("thumbnail", thumbnail, ["GET"], "Owned image preview"),
        ("references", upload, ["POST"], "Upload a reference image"),
        ("tasks", submit, ["POST"], "Submit an asynchronous generation or edit"),
        ("generate", generate, ["POST"], "Synchronous generation or edit"),
    ):
        web.register_web_api(endpoint, guarded(handler), methods, description)
