---
name: image-generation-plugin
description: Image studio with prompt templates, reference images, iterative edits, Redis task history and usage analytics.
---

## Description
Use this plugin for text-to-image generation via OpenAI Images compatible APIs.

## Capabilities
- Commands: /draw, /edit, /image-prompt, /image-status, /imagine
- Web page: Image Studio provides templates, reference upload, generation, iterative edits, private task history and aggregate usage charts, in English and Chinese
- Storage: the host's per-plugin storage service (private directory plus a private Redis key namespace); the plugin builds no connection and names no host path
- Decorated class tools: image_generate_tool, image_edit_tool
- Decorated function tool: image_prompt_tool
- Explicitly registered tool: image_plugin_status_tool
- Decorated SubAgent: image_art_director with a restricted tool registry
- Hooks: before_route hints and after_node_execute result enrichment
- Skill registration: this SKILL.md file

## Usage Hints
- Use /draw <prompt> to generate a new image via /v1/images/generations.
- Image editing picks its transport automatically: multipart /images/edits where the provider has it, otherwise the unified /images endpoint with the source image as an input reference. Set openai_images.edit_transport to pin one.
- Use Image Studio to submit asynchronous generation/edit tasks without an LLM turn; all requests use the authenticated host bridge.
- Select a generated result to edit it further; preserve its parent task ID for version lineage.
- Storage is supplied by the host through runtime_context; the plugin configures no Redis URL of its own.
- Read the plugin README for statistics definitions and API contracts.
- Use /edit <prompt> to edit an image: attach it to the message, or pass image_path for one of this plugin's own images. The tool reads the attached image from the message content parts, so no path has to be written by hand.
- Use /image-prompt <prompt> for an offline function-tool example.
- Use /image-status to inspect safe runtime/plugin metadata.
- Use /imagine <brief> to exercise Hook -> Planner -> SubAgent -> restricted Tool flow.
