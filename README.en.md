# Image Studio · image-generation-plugin

> 中文: [README.md](README.md)

A plugin with its own page, web API and image tools. The host provides plugin registration,
authentication, the tool executor, the page bridge and a generic per-plugin storage service; the
plugin adds no host business API and no host database table. The layout follows
[plugin-template](https://github.com/sxf51/plugin-template).

The page is bilingual: static text uses `data-i18n` keys and the backend returns only message
codes (`prompt_required`, `task_failed`, ...), rendered in the language the bridge reports.

## Features

- **Prompt templates** - 12 original parameterized templates across e-commerce, ads, posters,
  portraits, characters, UI, infographics, social covers and four edit types.
- **Reference images** - upload PNG / JPEG / WebP (up to 8 MiB, 20 megapixels) or pick an earlier
  output. The backend re-encodes to PNG and trusts neither the client file name nor its MIME type.
- **Iterative editing** - edit an output again; each task records `parent_id` and reference ids.
- **History** - search by status and prompt, 20 per page, reuse parameters or retry.
- **Statistics** - task totals, 7 / 30 / 90-day usage, active users, successes and failures, cache
  hits, new outputs and edits, with a daily chart.
- **Asynchronous submission** - the page gets 202 immediately, at most 3 concurrent tasks per user;
  leaving the page does not cancel a task, and interrupted tasks are never retried automatically.

## Files

| File | Contents |
| --- | --- |
| `plugin.yaml` | Manifest: metadata, `ui.pages`, `ui.panels`, `config.commands`, `config.tool_access` |
| `requirements.txt` | Runtime dependencies |
| `_conf_schema.json` | Generation, provider, output and LLM settings |
| `SKILL.md` | Skill description |
| `hooks.py` | `before_route` and `after_node_execute` |
| `tools.py` | Generate, edit, prompt and status tools |
| `subagents.py` | `image_art_director` |
| `web.py` | The studio's endpoints |
| `studio.py` | Task ledger, assets and statistics on host storage, loaded by path |
| `templates.json` | Prompt templates |
| `pages/gallery/` | The studio page |
| `main.py` | Run the plugin without the host: `inspect` / `doctor` / `call` / `web` / `serve` |
| `tests/test_studio.py`, `tests/studio-ui.test.mjs` | This plugin's behaviour |
| `tests/test_plugin_contract.py`, `tests/harness/`, `.github/` | Unchanged from the template |

## Storage

Everything goes through `runtime_context["storage"]`, already scoped to this plugin:
generated and reference images under `storage.dir("images")`, task metadata, indexes, statistics
and the TTL generation cache under `storage.key(...)`. Image-to-image accepts this plugin's own
outputs (`storage.resolve`) and files the user attached in chat (`storage.user_file`); any other
path is refused. When storage is unavailable the endpoints answer `storage_unavailable` with 503.

## Approval

`image_generate_tool` and `image_edit_tool` call a paid provider and write files, so they declare
`consequential = True`: `/draw`, `/edit` and planned calls go through the host's approval gate.
Pressing generate on the studio page is the user's approval, so `web.py` passes
`authorization_context={"approved_tool_calls": [tool_name]}` and page submissions are not paused.
A deployment that does not want approval lists both tools under `tools.approval_exempt_tools` in
the host's `config.yaml`.

## Configuration

Enter the image service key in the plugin's "API key" field. The service must support the
OpenAI Images compatible `/images/generations`. Edits use `openai_images.edit_transport`:

| Value | Behaviour |
| --- | --- |
| `auto` (default) | Multipart `/images/edits`; on 404 / 405 fall back to `input_references` |
| `images_edits` | Always multipart `/images/edits` |
| `input_references` | Always `POST {api_base}/images` with `data:` URLs in `input_references` (no mask support) |

## Development

In the plugin directory:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run python main.py doctor
```

In the host repository (the real `PluginManager`):

```bash
uv run pytest plugins/image-generation-plugin/tests -q
uv run ruff check plugins/image-generation-plugin --no-respect-gitignore
node --test plugins/image-generation-plugin/tests/studio-ui.test.mjs
```

The storage integration tests start a private `redis-server` on a free port and skip when it is
not installed. No test calls a paid image API.

To release, bump `version` in `plugin.yaml` and merge; `release.yml` tags `v<version>`.
