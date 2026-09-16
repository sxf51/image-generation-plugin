"""Offline behavioral tests for the plugin-owned studio."""

import asyncio
import base64
import importlib.util
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from urllib import error

import pytest
import redis
from PIL import Image

# These storage-integration tests exercise the host's Redis-backed storage
# factory.  The standalone template harness has no equivalent host module;
# its generic contract tests cover the plugin without requiring the monorepo.
pytest.importorskip("extension.plugin_storage")

from extension.plugin_storage import PluginStorageFactory

ROOT = Path(__file__).resolve().parents[1]


_MODULES = {}


def load(name):
    """Load a plugin module once per session so class identities stay stable across calls."""
    module = _MODULES.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location("studio_test_" + name, ROOT / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULES[name] = module
    return module


class Request:
    def __init__(self, body=None, user="alice", **query):
        self.body = body
        self.username = user
        self.query = query

    async def json(self, default=None):
        return self.body if self.body is not None else default


class Registry:
    def __init__(self):
        self.handlers = {}

    def register_web_api(self, name, handler, *_):
        self.handlers[name] = handler


def unpack(response):
    return json.loads(response.body) if hasattr(response, "body") else response


@pytest.fixture
def setup(tmp_path, monkeypatch, redis_url):
    """Wire the plugin exactly the way the host does: one scoped storage object, nothing else."""
    monkeypatch.chdir(tmp_path)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    # The key namespace is now bound to the plugin, not to a throwaway directory, so
    # start each test from an empty database on the isolated test server.
    redis.Redis.from_url(redis_url).flushdb()
    storage = PluginStorageFactory(data_root=tmp_path / "data", user_files_root=uploads, redis_url=redis_url)(
        "image-generation-plugin"
    )
    output = storage.dir("images")
    plugin = SimpleNamespace(name="image-generation-plugin", config={"output": {"keep_last": 200}})
    module = load("web")
    calls = []

    class Executor:
        async def execute(self, tool, payload, **kwargs):
            calls.append((tool, payload, kwargs))
            image = output / ("result-" + str(len(calls)) + ".png")
            Image.new("RGB", (12, 12), "red").save(image)
            return {"status": "success", "images": [str(image)], "model": "test-model", "source": "provider"}

    registry = Registry()
    module.register_web_apis(registry, plugin, {"tool_executor": Executor(), "storage": storage})
    yield registry.handlers, module._studio.Store(storage), calls, plugin, storage
    # Release the pooled connection before the session's Redis server goes away.
    storage.close()


def image_data():
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), "blue").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_details_page_api_key_is_read_from_plugin_config():
    tools = load("tools")
    config = {"openai_images": {"api_key": "details-page-key"}}
    assert tools._load_api_key(config) == "details-page-key"


def test_missing_details_page_api_key_is_rejected():
    tools = load("tools")
    with pytest.raises(ValueError, match="plugin details page"):
        tools._load_api_key({"openai_images": {"api_key": ""}})


@pytest.mark.asyncio
async def test_upload_edit_lineage_and_ownership(setup):
    api, ledger, calls, _, _ = setup
    asset = unpack(await api["references"](Request({"data": image_data()})))
    assert ledger.asset(asset["id"], "alice")
    assert not ledger.asset(asset["id"], "bob")
    assert (await api["thumbnail"](Request(user="bob", id=asset["id"]))).status_code == 404
    assert (await api["thumbnail"](Request(id=asset["id"]))).media_type == "image/jpeg"
    result = unpack(await api["generate"](Request({"prompt": "make it green", "reference": asset["id"]})))
    assert calls[0][0] == "image_edit_tool"
    assert Path(calls[0][1]["image_path"]).is_file()
    task = result["task"]
    child = unpack(
        await api["generate"](
            Request({"prompt": "make it gold", "reference": task["images"][0]["id"], "parent_id": task["id"]})
        )
    )
    assert child["task"]["parent_id"] == task["id"]
    assert (await api["history"](Request(user="bob", id=task["id"]))).status_code == 404
    assert (await api["gallery"](Request(user="bob")))["items"] == []
    assert str(ledger.root) not in json.dumps(child)


@pytest.mark.asyncio
async def test_async_submission_and_reopen(setup):
    api, ledger, calls, _plugin, storage = setup
    result = await api["tasks"](Request({"prompt": "a cat"}))
    assert result.status_code == 202
    task_id = unpack(result)["id"]
    for _ in range(30):
        await asyncio.sleep(0.01)
        if ledger.get(task_id, "alice")["status"] == "success":
            break
    reopened = load("studio").Store(storage)
    assert reopened.get(task_id, "alice")["status"] == "success"
    assert calls[0][0] == "image_generate_tool"
    assert calls[0][1]["actor_id"] == "alice"
    assert reopened.gallery("alice")[0]["task_id"] == task_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {"prompt": ""},
        {"prompt": "x", "image_count": 5},
        {"prompt": "x", "image_count": True},
        {"prompt": "x", "size": "evil"},
        {"prompt": "x", "reference": "../../secret"},
        {"prompt": "x", "parent_id": "missing"},
        {"prompt": "x", "template_id": "background"},
        {"prompt": "x", "template_id": "unknown"},
    ],
)
async def test_invalid_submissions_do_not_call_provider(setup, body):
    api, _, calls, _, _ = setup
    response = await api["tasks"](Request(body))
    assert response.status_code in (404, 422)
    assert calls == []


@pytest.mark.asyncio
async def test_upload_validation(setup):
    api, _, _, _, _ = setup
    for data in ("not base64!", base64.b64encode(b"not an image").decode()):
        assert (await api["references"](Request({"data": data}))).status_code == 422
    assert (await api["references"](Request({"data": "x" * (12 * 1024 * 1024)}))).status_code == 413


def test_stats_failure_cache_and_missing_outputs(setup):
    _, ledger, _, _, _ = setup
    for owner, source, status in [
        ("alice", "provider", "success"),
        ("alice", "cache", "success"),
        ("bob", "provider", "error"),
        ("unknown", "provider", "error"),
    ]:
        task_id = ledger.create(owner, "generate", {"prompt": "cat"})
        ledger.finish(task_id, owner, {"status": status, "source": source})
    stats = ledger.stats(7)
    assert stats["total_tasks"] == 4
    assert stats["uses"] == 4
    assert stats["active_users"] == 2
    assert stats["cache_hits"] == 1
    assert stats["failed"] == 2
    assert len(stats["series"]) == 7
    assert sum(day["uses"] for day in stats["series"]) == 4
    assert sum(day["uses"] for day in stats["series"][:-1]) == 0
    assert ledger.history("alice", search="CAT")["total"] == 2
    assert ledger.history("alice", status="error")["total"] == 0


def test_expiration_and_atomic_limit(setup):
    _, ledger, _, _, _ = setup
    ids = [ledger.create("alice", "generate", {"prompt": "x"}, "queued", max_pending=3) for _ in range(4)]
    assert all(ids[:3])
    assert ids[3] is None
    ledger.redis.zadd(ledger.key("pending"), {ids[0]: 0})
    ledger.expire(600)
    assert ledger.get(ids[0], "alice")["status"] == "interrupted"
    assert ledger.get(ids[1], "alice")["status"] == "queued"
    assert ledger.create("alice", "generate", {"prompt": "x"}, "queued", max_pending=3)


@pytest.mark.asyncio
async def test_provider_failure_is_recorded_without_exposing_paths(setup):
    _, ledger, _, plugin, storage = setup
    registry = Registry()

    class Executor:
        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("secret-token /private/provider.json")

    load("web").register_web_apis(registry, plugin, {"tool_executor": Executor(), "storage": storage})
    response = await registry.handlers["generate"](Request({"prompt": "x"}))
    assert response.status_code == 422
    assert "secret-token" not in response.body.decode()
    assert ledger.history("alice")["items"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_missing_output_retains_history(setup):
    api, ledger, _, _, _ = setup
    result = unpack(await api["generate"](Request({"prompt": "cat"})))
    asset = result["task"]["images"][0]
    ledger.resolve(asset["name"]).unlink()
    history = await api["history"](Request())
    assert not history["items"][0]["images"][0]["available"]
    assert (await api["gallery"](Request()))["items"] == []
    assert (await api["tasks"](Request({"prompt": "edit", "reference": asset["id"]}))).status_code == 404


@pytest.mark.asyncio
async def test_tools_tracking_cache_scoping_and_deleted_cache(setup, monkeypatch):
    _, ledger, _, plugin, storage = setup
    tools = load("tools")
    monkeypatch.setattr(tools, "_load_api_key", lambda _: "test")
    count = []

    def generate(**kwargs):
        count.append(kwargs)
        return [base64.b64decode(image_data())], None

    monkeypatch.setattr(tools, "_openai_generate", generate)
    tool = tools.ImageGenerateTool(plugin=plugin, runtime_context={"storage": storage})
    first = await tool.execute({"prompt": "cat", "actor_id": "alice"})
    second = await tool.execute({"prompt": "cat", "actor_id": "alice"})
    assert second["source"] == "cache"
    await tool.execute({"prompt": "cat", "actor_id": "bob"})
    assert len(count) == 2
    Path(first["images"][0]).unlink()
    third = await tool.execute({"prompt": "cat", "actor_id": "alice"})
    assert third["source"] == "provider"
    assert ledger.stats()["total_tasks"] == 4
    assert ledger.stats()["active_users"] == 2
    assert ledger.stats()["output_images"] == 3


def test_reference_retention_and_path_traversal(setup):
    _, ledger, _, _, _ = setup
    reference = ledger.root / "reference-keep.png"
    reference.write_bytes(base64.b64decode(image_data()))
    (ledger.root / "output.png").write_bytes(reference.read_bytes())
    load("tools")._prune_old_outputs(ledger.root, 0)
    assert reference.exists()
    assert not (ledger.root / "output.png").exists()
    assert ledger.resolve("../secret") is None
    assert ledger.resolve("..\\secret") is None


@pytest.mark.asyncio
async def test_templates_and_statistics_validation(setup):
    api, _, _, _, _ = setup
    templates = (await api["templates"](Request()))["items"]
    assert len(templates) >= 12
    assert len({t["id"] for t in templates}) == len(templates)
    assert any(t["requires_reference"] for t in templates)
    assert (await api["stats"](Request(days="90")))["days"] == 90
    assert (await api["stats"](Request(days="999"))).status_code == 422


def test_redis_cache_ttl_and_idempotent_finish(setup):
    _, ledger, _, _, _ = setup
    options = {"prompt": "cat", "model": "test", "size": "1024x1024"}
    image = ledger.root / "cat.png"
    image.write_bytes(base64.b64decode(image_data()))
    ledger.cache_set(paths=[str(image)], ttl_seconds=60, **options)
    assert 0 < ledger.redis.ttl(ledger.cache_key(**options)) <= 60
    assert ledger.cache_get(**options) == [str(image)]
    task_id = ledger.create("alice", "generate", {"prompt": "cat"})
    result = {"status": "success", "images": [str(image)]}
    ledger.finish(task_id, "alice", result)
    ledger.finish(task_id, "alice", result)
    assert ledger.redis.zcard(ledger.owner_key("alice", "assets:output")) == 1
    assert ledger.redis.zcard(ledger.owner_key("alice", "pending")) == 0


def test_concurrent_submissions_respect_redis_limit(setup):

    _, ledger, _, _, _ = setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: ledger.create("alice", "generate", {"prompt": "cat"}, max_pending=3), range(8)))
    assert len([task_id for task_id in ids if task_id]) == 3
    assert ledger.stats()["total_tasks"] == 3


@pytest.mark.asyncio
async def test_redis_unavailable_returns_503_without_provider_call(setup, monkeypatch):

    api, _, calls, _, _ = setup
    monkeypatch.setattr(redis.Redis, "zrangebyscore", lambda *_a, **_k: (_ for _ in ()).throw(redis.ConnectionError()))
    response = await api["tasks"](Request({"prompt": "cat"}))
    assert response.status_code == 503
    assert calls == []


def test_store_requires_a_storage_service():
    """Without a host storage object the plugin degrades loudly, it does not invent a location."""
    with pytest.raises(load("studio").StorageUnavailable):
        load("studio").Store(None)


@pytest.mark.asyncio
async def test_edit_accepts_a_host_uploaded_image(setup, monkeypatch, tmp_path):
    """An image the user attached in chat reaches the edit tool through content parts."""
    _, _, _, plugin, storage = setup
    tools = load("tools")
    monkeypatch.setattr(tools, "_load_api_key", lambda _: "test")
    seen = {}

    def edit(**kwargs):
        seen.update(kwargs)
        return [base64.b64decode(image_data())], None

    monkeypatch.setattr(tools, "_openai_edit", edit)
    upload = tmp_path / "uploads" / "photo.png"
    upload.write_bytes(base64.b64decode(image_data()))
    tool = tools.ImageEditTool(plugin=plugin, runtime_context={"storage": storage})
    result = await tool.execute(
        {
            "prompt": "make it warmer",
            "actor_id": "alice",
            "content_parts": [{"type": "text", "text": "make it warmer"}, {"type": "image", "url": str(upload)}],
        }
    )
    assert result["status"] == "success"
    assert Path(seen["image_path"]) == upload.resolve()


@pytest.mark.asyncio
async def test_edit_refuses_a_path_outside_host_storage(setup, tmp_path):
    """A path the host never handed out is refused even when the model asks for it."""
    _, _, _, plugin, storage = setup
    outsider = tmp_path / "outside.png"
    outsider.write_bytes(base64.b64decode(image_data()))
    tool = load("tools").ImageEditTool(plugin=plugin, runtime_context={"storage": storage})
    result = await tool.execute({"prompt": "x", "actor_id": "alice", "image_path": str(outsider)})
    assert result["status"] == "error"
    assert result["error_code"] == "source_image_unavailable"


# ---------------------------------------------------------------------------
# Editing transport
#
# The OpenAI Images contract puts editing on multipart /images/edits. Aggregators
# such as OpenRouter do not expose that endpoint at all (a plain 404) and hang
# image-to-image off a unified /images endpoint that takes the source image as an
# inline input reference instead. "auto" has to find the working one by itself.
# ---------------------------------------------------------------------------


def _http_error(code):
    return error.HTTPError("https://provider.test/images/edits", code, "boom", None, None)


def test_auto_transport_falls_back_when_the_edits_endpoint_is_absent(monkeypatch):
    tools = load("tools")
    seen = []
    monkeypatch.setattr(tools, "_openai_edit", lambda **_: (_ for _ in ()).throw(_http_error(404)))
    monkeypatch.setattr(
        tools, "_openai_edit_via_references", lambda **kwargs: seen.append(kwargs) or ([b"png"], "note")
    )

    images, note = tools._run_edit(
        transport="auto",
        base_url="https://provider.test",
        api_key="k",
        model="m",
        prompt="p",
        image_path="a.png",
        mask_path=None,
        image_count=1,
        size="1024x1024",
        timeout_seconds=5.0,
        allow_private_download_urls=False,
        max_download_bytes=10,
    )

    assert images == [b"png"]
    assert note == "note"
    assert len(seen) == 1
    assert seen[0]["image_path"] == "a.png"


@pytest.mark.parametrize("code", [401, 429, 500])
def test_auto_transport_does_not_mask_a_real_provider_failure(monkeypatch, code):
    """Only a missing endpoint triggers the fallback; other failures must surface."""
    tools = load("tools")
    monkeypatch.setattr(tools, "_openai_edit", lambda **_: (_ for _ in ()).throw(_http_error(code)))
    monkeypatch.setattr(tools, "_openai_edit_via_references", lambda **_: pytest.fail("must not fall back"))

    with pytest.raises(error.HTTPError):
        tools._run_edit(
            transport="auto",
            base_url="https://provider.test",
            api_key="k",
            model="m",
            prompt="p",
            image_path="a.png",
            mask_path=None,
            image_count=1,
            size="1024x1024",
            timeout_seconds=5.0,
            allow_private_download_urls=False,
            max_download_bytes=10,
        )


def test_auto_transport_refuses_to_silently_drop_a_mask(monkeypatch):
    """The unified endpoint has no mask, so editing the whole image instead is wrong."""
    tools = load("tools")
    monkeypatch.setattr(tools, "_openai_edit", lambda **_: (_ for _ in ()).throw(_http_error(404)))
    monkeypatch.setattr(tools, "_openai_edit_via_references", lambda **_: pytest.fail("must not fall back"))

    with pytest.raises(ValueError, match="mask"):
        tools._run_edit(
            transport="auto",
            base_url="https://provider.test",
            api_key="k",
            model="m",
            prompt="p",
            image_path="a.png",
            mask_path="m.png",
            image_count=1,
            size="1024x1024",
            timeout_seconds=5.0,
            allow_private_download_urls=False,
            max_download_bytes=10,
        )


def test_reference_transport_inlines_the_source_image(monkeypatch, tmp_path):
    """The source image travels as a data URL, since the provider cannot read a local path."""
    tools = load("tools")
    sent = {}
    monkeypatch.setattr(tools, "_http_json", lambda url, body, **kwargs: sent.update(url=url, body=body) or {})
    monkeypatch.setattr(tools, "_decode_image_payload", lambda *_, **__: ([b"png"], None))
    source = tmp_path / "reference-inline.png"
    source.write_bytes(base64.b64decode(image_data()))

    tools._openai_edit_via_references(
        base_url="https://provider.test",
        api_key="k",
        model="m",
        prompt="make it warmer",
        image_path=str(source),
        image_count=1,
        timeout_seconds=5.0,
    )

    assert sent["url"] == "https://provider.test/images"
    reference = sent["body"]["input_references"][0]
    assert reference["type"] == "image_url"
    assert reference["image_url"]["url"].startswith("data:image/png;base64,")
    assert "images/edits" not in sent["url"]


@pytest.mark.asyncio
async def test_failed_edit_records_an_actionable_code_without_leaking_the_provider_message(setup, monkeypatch):
    """The page needs to say *why* editing failed, without echoing the raw provider body."""
    _api, ledger, _calls, plugin, storage = setup
    tools = load("tools")
    monkeypatch.setattr(tools, "_load_api_key", lambda _: "test")
    monkeypatch.setattr(
        tools,
        "_run_edit",
        lambda **_: (_ for _ in ()).throw(
            error.HTTPError("https://provider.test/images/edits", 404, "/secret/path/провайдер", None, None)
        ),
    )
    reference = ledger.root / "reference-edit.png"
    reference.write_bytes(base64.b64decode(image_data()))
    asset = ledger.add_asset("alice", reference.name, "reference")

    tool = tools.ImageEditTool(plugin=plugin, runtime_context={"storage": storage})
    result = await tool.execute({"prompt": "x", "actor_id": "alice", "image_path": str(reference)})
    assert result["error_code"] == "provider_edit_unsupported"

    task_id = ledger.create("alice", "edit", {"prompt": "x"})
    ledger.finish(task_id, "alice", result)
    stored = ledger.get(task_id, "alice")
    assert stored["error"] == "provider_edit_unsupported"
    assert "/secret/path" not in json.dumps(stored, ensure_ascii=False)
    assert asset["name"] == reference.name
