"""Decorator-based SubAgent example for image planning."""

from __future__ import annotations

from typing import Any

from extension.plugin import plugin_subagent


@plugin_subagent(
    "image_art_director",
    domain="image",
    capabilities=("prompt-design", "generation-planning", "edit-planning"),
    tools=("image_prompt_tool", "image_generate_tool", "image_edit_tool", "image_plugin_status_tool"),
)
class ImageArtDirector:
    """Build an executable image workflow using an injected restricted tool view."""

    def __init__(
        self,
        domain: str,
        capabilities: tuple[str, ...],
        plugin: Any | None = None,
        runtime_context: dict[str, Any] | None = None,
        tools: Any | None = None,
        **_: Any,
    ) -> None:
        self.domain = domain
        self.capabilities = capabilities
        self.plugin = plugin
        self.runtime_context = runtime_context or {}
        self.tools = tools

    async def run(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        _ = (context, decision)
        query = str(task.get("query", "")).strip()
        trace_id = str(task.get("trace_id", "trace-image-art-director"))
        image_path = str(task.get("image_path", "")).strip()
        registry = self.tools or self.runtime_context.get("tool_registry")
        prompt_tool = registry.get("image_prompt_tool") if registry is not None else None
        if prompt_tool is None:
            return {
                "status": "error",
                "subagent": "image_art_director",
                "trace_id": trace_id,
                "error": "image_prompt_tool is unavailable",
            }
        prompt_result = await prompt_tool.execute({"query": query, "style": task.get("style", "cinematic")})
        selected_tool = "image_edit_tool" if image_path else "image_generate_tool"
        return {
            "status": "success",
            "subagent": "image_art_director",
            "trace_id": trace_id,
            "domain": self.domain,
            "capabilities": list(self.capabilities),
            "selected_tool": selected_tool,
            "tool_payload": {
                "prompt": prompt_result.get("prompt", query),
                **({"image_path": image_path} if image_path else {}),
            },
            "report": f"Prepared an image workflow using {selected_tool}.",
        }


def register_subagents(subagent_registry: Any, plugin: Any, runtime_context: dict[str, Any]) -> None:
    """Explicit entrypoint coexists with decorator discovery."""
    _ = subagent_registry
    _ = plugin
    _ = runtime_context
