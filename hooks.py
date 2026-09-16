"""Lifecycle hook examples for the image reference plugin."""

from __future__ import annotations

from typing import Any

from extension.hook import HookPoint


def register_hooks(hook_manager: Any, plugin: Any, runtime_context: dict[str, Any]) -> None:
    """Register inbound-routing and node-result enrichment hooks."""
    _ = runtime_context
    plugin_name = str(getattr(plugin, "name", "image-generation-plugin"))

    async def before_route(context: dict[str, Any]) -> dict[str, Any]:
        updated = dict(context)
        message = updated.get("message")
        query = str(message.get("text", "") if isinstance(message, dict) else "").strip()
        if query.lower().startswith(("/imagine", "/image-plan")):
            updated["router_hints"] = {
                "plugin": plugin_name,
                "preferred_route": "subagent",
                "preferred_subagent": "image_art_director",
                "fallback_route": "tool",
                "fallback_tool": "image_prompt_tool",
            }
        return updated

    async def after_node_execute(context: dict[str, Any]) -> dict[str, Any]:
        updated = dict(context)
        result = updated.get("result")
        node = updated.get("node")
        runtime_config = node.get("runtime_config", {}) if isinstance(node, dict) else {}
        target = str(runtime_config.get("target", "")) if isinstance(runtime_config, dict) else ""
        is_image_result = target.startswith("image_") or (
            isinstance(result, dict) and str(result.get("tool", "")).startswith("image_")
        )
        if isinstance(result, dict) and is_image_result:
            enriched = dict(result)
            enriched.setdefault("plugin", plugin_name)
            enriched.setdefault("extension_method", "after_node_execute_hook")
            updated["result"] = enriched
        return updated

    hook_manager.register(plugin_name, HookPoint.before_route, before_route, priority=30)
    hook_manager.register(plugin_name, HookPoint.after_node_execute, after_node_execute, priority=90)
