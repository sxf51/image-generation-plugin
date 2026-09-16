"""The page's synchronous `generate` endpoint, with the task ledger stubbed out.

`test_studio.py` covers the ledger against a real Redis. These tests pin the
boundary between the page and the tool executor and need no Redis at all, so
they run everywhere, CI included.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PLUGIN = SimpleNamespace(name="image-generation-plugin", config={})


class _Request:
    def __init__(self, body: Any, username: str = "alice") -> None:
        self.body = body
        self.username = username
        self.query: dict[str, str] = {}

    async def json(self, default: Any = None) -> Any:
        return self.body if self.body is not None else default


class _Registry:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def register_web_api(self, endpoint: str, handler: Any, _methods: Any = None, _description: str = "") -> None:
        self.handlers[endpoint] = handler


def _web_module() -> Any:
    spec = importlib.util.spec_from_file_location("image_generation_plugin_page_test_web", PLUGIN_DIR / "web.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    ledger = MagicMock()
    ledger.create.return_value = "test-task"
    ledger.get.return_value = {"id": "test-task"}
    ledger.gallery.return_value = []
    module._studio.Store = MagicMock(return_value=ledger)
    return module


def _generate(runtime_context: dict[str, Any], body: Any, username: str = "alice") -> Any:
    registry = _Registry()
    _web_module().register_web_apis(registry, PLUGIN, runtime_context)
    return asyncio.run(registry.handlers["generate"](_Request(body, username)))


def _body(response: Any) -> Any:
    """Read a helper response, whichever backend produced it."""
    content = getattr(response, "content", None)
    if content is not None:
        return content
    return json.loads(bytes(response.body))


def test_generate_requires_a_prompt() -> None:
    class Executor:
        async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("the tool must not run for an empty prompt")

    response = _generate({"tool_executor": Executor()}, {})
    assert response.status_code == 422
    # A message code, rendered by the page in the reader's language.
    assert _body(response) == {"status": "error", "message": "prompt_required"}


def test_generate_requires_the_executor() -> None:
    assert _generate({}, {"prompt": "a cat"}).status_code == 503


def test_generate_calls_the_tool_and_hides_server_paths() -> None:
    calls: list[tuple[Any, ...]] = []

    class Executor:
        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            calls.append((args, kwargs))
            return {
                "status": "success",
                "report": "ok",
                "images": ["D:/private/cat.png"],
                "attachments": [{"path": "D:/private/cat.png"}],
            }

    response = _generate({"tool_executor": Executor()}, {"prompt": "a cat", "size": "1536x1024"}, "bob")

    assert response.status_code == 200
    body = _body(response)
    assert body["status"] == "success"
    assert "images" not in body
    assert body["items"] == []
    (tool, payload), kwargs = calls[0]
    assert tool == "image_generate_tool"
    assert payload["prompt"] == "a cat"
    assert payload["size"] == "1536x1024"
    assert payload["actor_id"] == "bob"
    assert kwargs["trace_id"].startswith("plugin-page:image-generation-plugin:bob")
    assert kwargs["authorization_context"] == {"approved_tool_calls": ["image_generate_tool"]}


def test_generate_does_not_echo_provider_errors() -> None:
    class Executor:
        async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            return {"status": "error", "report": "provider unavailable", "error": "offline"}

    response = _generate({"tool_executor": Executor()}, {"prompt": "a cat"})
    assert response.status_code == 422
    body = _body(response)
    assert body["status"] == "error"
    assert "provider unavailable" not in json.dumps(body)
