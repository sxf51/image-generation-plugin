"""Tools for image-generation-plugin.

Features:
1. /draw command parsing for image prompt extraction.
2. Provider routing: OpenAI Images compatible endpoint.
3. Structured result payload with saved local file paths and failure diagnostics.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import ipaddress
import json
import mimetypes
import re
import socket
import time
import uuid
from functools import wraps
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from extension.plugin import plugin_tool

_studio_spec = importlib.util.spec_from_file_location("image_studio_tool_store", Path(__file__).with_name("studio.py"))
_studio = importlib.util.module_from_spec(_studio_spec)
_studio_spec.loader.exec_module(_studio)


def _tracked(mode):
    def decorate(method):
        @wraps(method)
        async def execute(self, payload):
            # Page submissions are recorded at the executor boundary, including executor failures.
            if payload.get("source") == "plugin-page":
                return await method(self, payload)
            ledger = _studio.Store(self.storage)
            owner = str(payload.get("actor_id") or "unknown")
            normalized = dict(payload)
            normalized["prompt"] = _extract_prompt(payload, _resolve_query(payload))
            options = _generation_options(_plugin_config(self.plugin), payload)
            normalized.update(size=options["size"], image_count=options["image_count"])
            task_id = await asyncio.to_thread(ledger.create, owner, mode, normalized)
            try:
                result = await method(self, payload)
            except BaseException:
                await asyncio.to_thread(ledger.finish, task_id, owner, {"status": "error"})
                raise
            await asyncio.to_thread(ledger.finish, task_id, owner, result)
            result["task_id"] = task_id
            return result

        return execute

    return decorate


_COMMAND_PREFIX_PATTERN = re.compile(r"^/(?:draw|edit|image-prompt|imagine)\b", re.IGNORECASE)
_DEFAULT_TIMEOUT_SECONDS = 45.0
_DEFAULT_IMAGE_COUNT = 1
_DEFAULT_SIZE = "1024x1024"
_DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"
_DEFAULT_OPENAI_MODEL = "gpt-image-1"
_DEFAULT_MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
_DEFAULT_HTTP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
    AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _trace_id(payload: dict[str, object], default_value: str) -> str:
    return str(payload.get("trace_id", default_value))


def _resolve_query(payload: dict[str, object]) -> str:
    query = str(payload.get("query", "")).strip()
    if query:
        return query
    for key in ("query_raw", "text", "message", "prompt", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_prompt(payload: dict[str, object], query: str) -> str:
    explicit_prompt = str(payload.get("prompt", "")).strip()
    if explicit_prompt:
        return explicit_prompt

    normalized = query.strip()
    if normalized.startswith("/"):
        return _COMMAND_PREFIX_PATTERN.sub("", normalized, count=1).strip()
    return normalized


def _plugin_config(plugin: Any | None) -> dict[str, Any]:
    cfg = getattr(plugin, "config", {}) if plugin is not None else {}
    return cfg if isinstance(cfg, dict) else {}


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _generation_options(config: dict[str, Any], payload: dict[str, object]) -> dict[str, Any]:
    generation_cfg = config.get("generation", {}) if isinstance(config.get("generation", {}), dict) else {}
    timeout_seconds = _coerce_float(
        payload.get("timeout_seconds", generation_cfg.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)),
        _DEFAULT_TIMEOUT_SECONDS,
    )
    provider = str(payload.get("provider", generation_cfg.get("provider", "openai_images"))).strip().lower()
    model = str(payload.get("model", generation_cfg.get("model", _DEFAULT_OPENAI_MODEL))).strip()
    image_count = _coerce_int(
        payload.get("image_count", generation_cfg.get("image_count", _DEFAULT_IMAGE_COUNT)),
        _DEFAULT_IMAGE_COUNT,
    )
    size = str(payload.get("size", generation_cfg.get("size", _DEFAULT_SIZE))).strip()
    cache_ttl_seconds = _coerce_int(generation_cfg.get("cache_ttl_seconds", 1800), 1800)
    return {
        "timeout_seconds": max(1.0, timeout_seconds),
        "provider": provider or "openai_images",
        "model": model or _DEFAULT_OPENAI_MODEL,
        "image_count": max(1, min(image_count, 4)),
        "size": size or _DEFAULT_SIZE,
        "cache_ttl_seconds": max(1, cache_ttl_seconds),
    }


def _keep_last(config: dict[str, Any]) -> int:
    output_cfg = config.get("output", {}) if isinstance(config.get("output", {}), dict) else {}
    return max(20, _coerce_int(output_cfg.get("keep_last", 200), 200))


# 中文: 解析一张"要拿来改的图"。两个来源都由宿主背书, 插件自己不认路径:
#   - storage.resolve(): 这张图是本插件自己产出/保存的(画廊里的作品、参考图)
#   - storage.user_file(): 这张图是宿主替用户存下来的(聊天里刚上传的附件)
# 两者都不接受时返回 None, 调用方据此报 "image not found"。
def _resolve_image(storage: Any, raw_path: Any) -> Path | None:
    text = str(raw_path or "").strip()
    if not text or storage is None:
        return None
    return storage.resolve(text) or storage.user_file(text)


# 中文: 从这次请求的多模态内容片段里挑出用户带来的本地图片(分片 url 为本地路径的; 取最后一张,
# 也就是用户最新贴的那张)。DAG 路由下 content_parts 由 planner 铺进节点入参,
# ReAct 路由下由 orchestrator 通过 caller_context 注入, 两条路都到得了这里,
# 所以"以图生图"不再依赖模型把本地路径写进工具参数——它根本看不到路径。
def _image_paths_from_content(payload: dict[str, object]) -> list[str]:
    parts = payload.get("content_parts")
    if not isinstance(parts, list):
        return []
    found: list[str] = []
    for part in parts:
        if not isinstance(part, dict) or str(part.get("type") or "") != "image":
            continue
        raw = str(part.get("url") or "").strip()
        if raw and not raw.lower().startswith(("http://", "https://", "data:")):
            found.append(raw)
    return found


def _openai_options(config: dict[str, Any], selected_model: str) -> tuple[str, str]:
    openai_cfg = config.get("openai_images", {}) if isinstance(config.get("openai_images", {}), dict) else {}
    base_url = str(openai_cfg.get("api_base", _DEFAULT_OPENAI_BASE)).strip() or _DEFAULT_OPENAI_BASE
    fallback_model = selected_model or _DEFAULT_OPENAI_MODEL
    model = str(openai_cfg.get("model", fallback_model)).strip()
    return base_url.rstrip("/"), (model or _DEFAULT_OPENAI_MODEL)



def _load_api_key(config: dict[str, Any]) -> str:
    """Read the provider key saved by the plugin details form."""
    openai_cfg = config.get("openai_images", {}) if isinstance(config.get("openai_images", {}), dict) else {}
    value = str(openai_cfg.get("api_key", "") or "").strip()
    if not value:
        raise ValueError("missing api key; configure it on the plugin details page")
    return value


def _provider_settings(config: dict[str, Any], llm: Any | None, selected_model: str) -> tuple[str, str, str]:
    """Resolve either the host-provided model or the plugin-specific settings."""
    source = str(config.get("model_source") or "custom").strip()
    if source == "host_model":
        if llm is None:
            raise ValueError("host model is not configured")
        base_url = str(getattr(llm, "base_url", "") or "").strip()
        api_key = str(getattr(llm, "api_key", "") or "").strip()
        model = str(getattr(llm, "model", "") or selected_model).strip()
        if not base_url or not api_key or not model:
            raise ValueError("host model is not configured")
        return base_url.rstrip("/"), api_key, model
    if source != "custom":
        raise ValueError("unsupported model source")
    base_url, model = _openai_options(config, selected_model)
    api_key = _load_api_key(config)
    return base_url, api_key, model

_EDIT_TRANSPORTS = ("auto", "images_edits", "input_references")


# 中文: 读取改图传输方式配置。取值非法时回落到 auto, 而不是让插件启动失败。
def _edit_transport(config: dict[str, Any]) -> str:
    openai_cfg = config.get("openai_images", {}) if isinstance(config.get("openai_images", {}), dict) else {}
    value = str(openai_cfg.get("edit_transport", "auto")).strip().lower()
    return value if value in _EDIT_TRANSPORTS else "auto"


# 中文: 把一次 provider 失败归类成稳定的消息码, 供前端按读者语言渲染。
# 只回码、不回原始报错文本——原文里可能带服务端路径或密钥片段。
_HTTP_STATUS_CODES = {
    "unauthorized": (401, 403),
    "rate_limited": (429,),
}


def _provider_error_code(exc: BaseException) -> str:
    if isinstance(exc, error.HTTPError):
        for name, codes in _HTTP_STATUS_CODES.items():
            if exc.code in codes:
                return f"provider_{name}"
        return "provider_edit_unsupported" if exc.code in _EDIT_ENDPOINT_ABSENT else "provider_rejected"
    timed_out = isinstance(exc, TimeoutError) or (
        isinstance(exc, error.URLError) and isinstance(exc.reason, TimeoutError)
    )
    if timed_out:
        return "provider_timeout"
    if isinstance(exc, error.URLError):
        return "provider_unreachable"
    if isinstance(exc, ValueError) and "api key" in str(exc).casefold():
        return "missing_api_key"
    return "provider_failed"


def _http_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout_seconds: float) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("provider API URL must use http or https and include a hostname")
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = request.Request(url=url, data=raw, headers=headers, method="POST")
    try:
        # The provider endpoint scheme and hostname are checked above.
        with request.urlopen(req, timeout=timeout_seconds) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = "(could not read error body)"
        msg = f"HTTP {exc.code} from {url}: {error_body}"
        raise error.HTTPError(exc.url, exc.code, msg, exc.headers, None) from exc
    if not isinstance(payload, dict):
        msg = "provider response is not a JSON object"
        raise ValueError(msg)
    return payload


def _validate_download_url(url: str, *, allow_private: bool) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        msg = "image download URL must use http or https and include a hostname"
        raise ValueError(msg)
    if parsed.username is not None or parsed.password is not None:
        msg = "image download URL must not contain credentials"
        raise ValueError(msg)
    if allow_private:
        return

    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        msg = f"could not resolve image download host: {parsed.hostname}"
        raise ValueError(msg) from exc
    if not addresses:
        msg = f"image download host resolved to no addresses: {parsed.hostname}"
        raise ValueError(msg)
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            msg = f"image download URL resolves to a non-public address: {ip}"
            raise ValueError(msg)


def _read_limited(response: Any, *, max_bytes: int) -> bytes:
    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        msg = f"image download exceeded {max_bytes} bytes"
        raise ValueError(msg)
    return data


def _download_url(
    url: str,
    timeout_seconds: float,
    *,
    allow_private: bool = False,
    max_bytes: int = _DEFAULT_MAX_DOWNLOAD_BYTES,
) -> bytes:
    """Download image bytes from a URL."""
    _validate_download_url(url, allow_private=allow_private)

    class ValidatingRedirectHandler(request.HTTPRedirectHandler):
        def redirect_request(  # noqa: PLR0917
            self,
            req: request.Request,
            fp: Any,
            code: int,
            msg: str,
            headers: Any,
            newurl: str,
        ) -> request.Request | None:
            _validate_download_url(newurl, allow_private=allow_private)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    req = request.Request(
        url=url,
        headers={
            "User-Agent": _DEFAULT_HTTP_USER_AGENT,
            "Accept": "image/*,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        opener = request.build_opener(ValidatingRedirectHandler())
        with opener.open(req, timeout=timeout_seconds) as response:
            return _read_limited(response, max_bytes=max(1, max_bytes))
    except error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = "(could not read error body)"
        msg = f"HTTP {exc.code} while downloading image url {url}: {error_body}"
        raise error.HTTPError(exc.url, exc.code, msg, exc.headers, None) from exc


def _openai_generate(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    image_count: int,
    size: str,
    timeout_seconds: float,
    allow_private_download_urls: bool = False,
    max_download_bytes: int = _DEFAULT_MAX_DOWNLOAD_BYTES,
) -> tuple[list[bytes], str | None]:
    # dall-e-3 / gpt-image-2-all only supports n=1.
    actual_n = min(image_count, 1)
    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": actual_n,
        "size": size,
        # Do not send response_format. Provider may return either url or b64_json.
    }
    payload = _http_json(
        f"{base_url}/images/generations",
        body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        timeout_seconds=timeout_seconds,
    )

    images: list[bytes] = []
    note: str | None = None
    data = payload.get("data", [])
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            # Prefer b64_json, fall back to url.
            b64 = item.get("b64_json")
            if isinstance(b64, str) and b64.strip():
                images.append(base64.b64decode(b64))
            else:
                url = item.get("url")
                if isinstance(url, str) and url.strip():
                    images.append(
                        _download_url(
                            url.strip(),
                            timeout_seconds,
                            allow_private=allow_private_download_urls,
                            max_bytes=max_download_bytes,
                        )
                    )
            revised_prompt = item.get("revised_prompt")
            if isinstance(revised_prompt, str) and revised_prompt.strip() and not note:
                note = revised_prompt.strip()

    if not images:
        msg = "openai images returned no image bytes"
        raise ValueError(msg)
    return images, note


def _build_multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    """Build a multipart/form-data body for file upload requests."""
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for name, (filename, data) in files.items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                "Content-Type: image/png\r\n\r\n"
            ).encode()
            + data
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _openai_edit(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    image_path: str,
    mask_path: str | None,
    image_count: int,
    size: str,
    timeout_seconds: float,
    allow_private_download_urls: bool = False,
    max_download_bytes: int = _DEFAULT_MAX_DOWNLOAD_BYTES,
) -> tuple[list[bytes], str | None]:
    """Call /v1/images/edits with multipart/form-data."""
    fields = {
        "model": model,
        "prompt": prompt,
        "n": str(image_count),
        "size": size,
    }
    files: dict[str, tuple[str, bytes]] = {
        "image": (Path(image_path).name, Path(image_path).read_bytes()),
    }
    if mask_path:
        files["mask"] = (Path(mask_path).name, Path(mask_path).read_bytes())

    body, content_type = _build_multipart(fields, files)
    req = request.Request(
        url=f"{base_url}/images/edits",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": content_type},
        method="POST",
    )
    try:
        parsed = urlparse(req.full_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("provider API URL must use http or https and include a hostname")
        # The provider endpoint scheme and hostname are checked above.
        with request.urlopen(req, timeout=timeout_seconds) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = "(could not read error body)"
        msg = f"HTTP {exc.code} from {base_url}/images/edits: {error_body}"
        raise error.HTTPError(exc.url, exc.code, msg, exc.headers, None) from exc
    if not isinstance(payload, dict):
        msg = "provider response is not a JSON object"
        raise ValueError(msg)

    return _decode_image_payload(
        payload,
        timeout_seconds=timeout_seconds,
        allow_private_download_urls=allow_private_download_urls,
        max_download_bytes=max_download_bytes,
        label="openai images edit",
    )


# 中文: 把图像响应解析成字节+可选备注。生成/编辑/统一端点三条路径的响应体形状
# 相同(data 数组里带 b64_json 或 url)，共用一份解析逻辑。
def _decode_image_payload(
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
    allow_private_download_urls: bool,
    max_download_bytes: int,
    label: str,
) -> tuple[list[bytes], str | None]:
    images: list[bytes] = []
    note: str | None = None
    data = payload.get("data", [])
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            b64 = item.get("b64_json")
            if isinstance(b64, str) and b64.strip():
                images.append(base64.b64decode(b64))
            elif isinstance(item.get("url"), str) and item["url"].strip():
                images.append(
                    _download_url(
                        item["url"].strip(),
                        timeout_seconds,
                        allow_private=allow_private_download_urls,
                        max_bytes=max_download_bytes,
                    )
                )
            revised_prompt = item.get("revised_prompt")
            if isinstance(revised_prompt, str) and revised_prompt.strip() and not note:
                note = revised_prompt.strip()

    if not images:
        msg = f"{label} returned no image bytes"
        raise ValueError(msg)
    return images, note


# 中文: 以图生图的第二种传输方式——统一图像端点 POST {base}/images, 参考图用
# input_references 以 data: URL 内联传入。OpenAI 官方用 multipart 的
# /images/edits, 而 OpenRouter 这类聚合服务根本没有该端点(直接 404), 改图能力
# 挂在统一端点上。两种形状的响应体一致, 所以只有请求侧不同。
# 注意: 统一端点没有蒙版(mask)概念, 调用方需要在选择该传输前自行拒绝蒙版请求。
def _openai_edit_via_references(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    image_path: str,
    image_count: int,
    timeout_seconds: float,
    allow_private_download_urls: bool = False,
    max_download_bytes: int = _DEFAULT_MAX_DOWNLOAD_BYTES,
) -> tuple[list[bytes], str | None]:
    """Call {base}/images with the source image inlined as an input reference."""
    source = Path(image_path)
    mime_type = mimetypes.guess_type(source.name)[0] or "image/png"
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    payload = _http_json(
        f"{base_url}/images",
        {
            "model": model,
            "prompt": prompt,
            "n": image_count,
            "input_references": [{"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}}],
        },
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        timeout_seconds=timeout_seconds,
    )
    return _decode_image_payload(
        payload,
        timeout_seconds=timeout_seconds,
        allow_private_download_urls=allow_private_download_urls,
        max_download_bytes=max_download_bytes,
        label="unified images edit",
    )


# 中文: 选择并执行一次改图调用。
# transport=auto(默认): 先按 OpenAI 官方契约打 /images/edits; 该端点不存在
#   (404/405)时说明服务商把改图挂在统一端点上, 自动改走 input_references。
#   只在"端点不存在"时回退——其它 HTTP 错误(鉴权、超限、模型不支持)照常抛出,
#   否则真正的失败原因会被第二次调用掩盖。
# transport=images_edits / input_references: 固定走其中一种, 不做探测。
_EDIT_ENDPOINT_ABSENT = (404, 405)


def _run_edit(
    *,
    transport: str,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    image_path: str,
    mask_path: str | None,
    image_count: int,
    size: str,
    timeout_seconds: float,
    allow_private_download_urls: bool,
    max_download_bytes: int,
) -> tuple[list[bytes], str | None]:
    """Run one edit through the configured transport, probing for the OpenAI one when asked."""
    references_only = {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "prompt": prompt,
        "image_path": image_path,
        "image_count": image_count,
        "timeout_seconds": timeout_seconds,
        "allow_private_download_urls": allow_private_download_urls,
        "max_download_bytes": max_download_bytes,
    }
    if transport == "input_references":
        return _openai_edit_via_references(**references_only)

    try:
        return _openai_edit(
            base_url=base_url,
            api_key=api_key,
            model=model,
            prompt=prompt,
            image_path=image_path,
            mask_path=mask_path,
            image_count=image_count,
            size=size,
            timeout_seconds=timeout_seconds,
            allow_private_download_urls=allow_private_download_urls,
            max_download_bytes=max_download_bytes,
        )
    except error.HTTPError as exc:
        if transport != "auto" or exc.code not in _EDIT_ENDPOINT_ABSENT:
            raise
        if mask_path:
            # The unified endpoint has no mask; silently dropping one would edit
            # the whole image instead of the region the user marked.
            msg = "provider has no /images/edits endpoint, and its unified images endpoint does not accept a mask"
            raise ValueError(msg) from exc
    return _openai_edit_via_references(**references_only)


def _prune_old_outputs(output_dir: Path, keep_last: int) -> None:
    files = sorted(
        (p for p in output_dir.glob("*.png") if p.is_file() and not p.name.startswith("reference-")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in files[keep_last:]:
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            continue


def _persist_images(output_dir: Path, images: list[bytes], *, provider: str) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    result_paths: list[str] = []
    for idx, raw in enumerate(images, start=1):
        name = f"{provider}-{timestamp}-{uuid.uuid4().hex[:8]}-{idx}.png"
        path = output_dir / name
        path.write_bytes(raw)
        result_paths.append(str(path.resolve()))
    return result_paths


# 中文: 把"写盘 + 清理旧输出"打包成一个同步函数，方便调用方用
# asyncio.to_thread 一次性丢到工作线程，避免阻塞事件循环。
def _persist_and_prune(output_dir: Path, images: list[bytes], provider: str, keep_last: int) -> tuple[list[str], None]:
    paths = _persist_images(output_dir, images, provider=provider)
    _prune_old_outputs(output_dir, keep_last=keep_last)
    return paths, None


@plugin_tool(
    "image_generate_tool",
    tags=("image", "generation", "command"),
    metadata={
        "description": "Generate an image from a text prompt.",
        "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}}},
        "consequential": True,
    },
)
class ImageGenerateTool:
    """Generate images from text prompts via provider API."""

    def __init__(self, plugin: Any | None = None, runtime_context: dict[str, Any] | None = None, **_: Any) -> None:
        self.plugin = plugin
        # The host binds this plugin's directory and key namespace before handing
        # the object over, so nothing here knows where the data actually lives.
        self.storage = (runtime_context or {}).get("storage")
        self.llm = (runtime_context or {}).get("llm_config")

    @_tracked("generate")
    async def execute(self, payload: dict[str, object]) -> dict[str, object]:
        trace_id = _trace_id(payload, "trace-image-generate")
        query = _resolve_query(payload)
        prompt = _extract_prompt(payload, query)
        if not prompt:
            return {
                "status": "error",
                "tool": "image_generate_tool",
                "trace_id": trace_id,
                "query": query,
                "error_code": "missing_prompt",
                "error": "missing prompt",
                "report": "Image generation failed: prompt is required. Use /draw <prompt>.",
            }

        config = _plugin_config(self.plugin)
        options = _generation_options(config, payload)
        provider = str(options["provider"])
        model = str(options["model"])
        image_count = int(options["image_count"])
        size = str(options["size"])
        timeout_seconds = float(options["timeout_seconds"])
        cache_ttl_seconds = int(options["cache_ttl_seconds"])
        try:
            output_dir, keep_last = self.storage.dir("images"), _keep_last(config)
            base_url, _, model = _provider_settings(config, self.llm, model)
            cache_prompt = json.dumps(
                [prompt, str(payload.get("actor_id") or "unknown"), str(output_dir), base_url],
                ensure_ascii=False,
            )

            ledger = _studio.Store(self.storage)
            cached = await asyncio.to_thread(
                ledger.cache_get,
                provider=provider,
                model=model,
                prompt=cache_prompt,
                image_count=image_count,
                size=size,
            )
            if cached:
                return {
                    "status": "success",
                    "tool": "image_generate_tool",
                    "trace_id": trace_id,
                    "query": query,
                    "prompt": prompt,
                    "provider": provider,
                    "model": model,
                    "size": size,
                    "image_count": len(cached),
                    "images": cached,
                    "source": "cache",
                    "report": f"Generated image cache hit: {len(cached)} image(s).",
                }

            note: str | None = None
            if provider in {"openai", "openai_images", "openai-images"}:
                openai_base_url, api_key, openai_model = _provider_settings(config, self.llm, model)
                security_cfg = config.get("security", {}) if isinstance(config.get("security", {}), dict) else {}
                max_download_bytes = _coerce_int(
                    security_cfg.get("max_download_bytes", _DEFAULT_MAX_DOWNLOAD_BYTES),
                    _DEFAULT_MAX_DOWNLOAD_BYTES,
                )
                # 中文: provider 调用是同步阻塞的 urlopen(图像生成通常要数秒到
                # 数十秒)，必须丢到工作线程执行，否则整个事件循环会被这次
                # HTTP 请求占住，同进程内其它接口(如前端接口)全部卡死。
                binary_images, note = await asyncio.to_thread(
                    _openai_generate,
                    base_url=openai_base_url,
                    api_key=api_key,
                    model=openai_model,
                    prompt=prompt,
                    image_count=image_count,
                    size=size,
                    timeout_seconds=timeout_seconds,
                    allow_private_download_urls=security_cfg.get("allow_private_download_urls", False) is True,
                    max_download_bytes=max(1, max_download_bytes),
                )
                model = openai_model
                provider = "openai_images"
            else:
                msg = f"unsupported provider '{provider}'; only 'openai_images' is supported"
                raise ValueError(msg)

            # 中文: 落盘与清理旧文件同样是同步 I/O，一并放到线程里。
            image_paths, _ = await asyncio.to_thread(_persist_and_prune, output_dir, binary_images, provider, keep_last)
            await asyncio.to_thread(
                ledger.cache_set,
                ttl_seconds=cache_ttl_seconds,
                provider=provider,
                model=model,
                prompt=cache_prompt,
                image_count=image_count,
                size=size,
                paths=image_paths,
            )

            return {
                "status": "success",
                "tool": "image_generate_tool",
                "trace_id": trace_id,
                "query": query,
                "prompt": prompt,
                "provider": provider,
                "model": model,
                "size": size,
                "image_count": len(image_paths),
                "images": image_paths,
                "source": "provider",
                "note": note,
                "report": f"Image generated successfully: {len(image_paths)} file(s).",
            }
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
            return {
                "status": "error",
                "tool": "image_generate_tool",
                "trace_id": trace_id,
                "query": query,
                "prompt": prompt,
                "provider": provider,
                "model": model,
                "error_code": _provider_error_code(exc),
                "error": str(exc),
                "report": f"Image generation failed: {exc}",
            }


@plugin_tool(
    "image_edit_tool",
    tags=("image", "edit", "command"),
    metadata={
        "description": "Edit an existing image with a text instruction.",
        "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}}},
        "consequential": True,
    },
)
class ImageEditTool:
    """Edit an existing image via OpenAI /v1/images/edits."""

    def __init__(self, plugin: Any | None = None, runtime_context: dict[str, Any] | None = None, **_: Any) -> None:
        self.plugin = plugin
        self.storage = (runtime_context or {}).get("storage")
        self.llm = (runtime_context or {}).get("llm_config")

    @_tracked("edit")
    async def execute(self, payload: dict[str, object]) -> dict[str, object]:
        trace_id = _trace_id(payload, "trace-image-edit")
        query = _resolve_query(payload)
        prompt = _extract_prompt(payload, query)
        # 中文: 显式给的 image_path 优先; 没有就用这次用户消息里带的图片。
        # 聊天里"照着这张图改"根本不会有人手写路径, 模型也看不到路径。
        candidates = [str(payload.get("image_path", "")).strip(), *reversed(_image_paths_from_content(payload))]
        image_path = next((item for item in candidates if item), "")

        if not prompt:
            return {
                "status": "error",
                "tool": "image_edit_tool",
                "trace_id": trace_id,
                "error_code": "missing_prompt",
                "error": "missing prompt",
                "report": "Image edit failed: prompt is required. Use /edit <prompt> with an image.",
            }
        if not image_path:
            return {
                "status": "error",
                "tool": "image_edit_tool",
                "trace_id": trace_id,
                "error_code": "missing_source_image",
                "error": "missing source image",
                "report": "Image edit failed: attach the image to edit, or pick one from the gallery.",
            }
        mask_path = str(payload.get("mask_path", "")).strip() or None
        config = _plugin_config(self.plugin)
        options = _generation_options(config, payload)
        model = str(options["model"])
        image_count = int(options["image_count"])
        size = str(options["size"])
        timeout_seconds = float(options["timeout_seconds"])

        try:
            security_cfg = config.get("security", {}) if isinstance(config.get("security", {}), dict) else {}
            resolved_image = _resolve_image(self.storage, image_path)
            if resolved_image is None:
                return {
                    "status": "error",
                    "tool": "image_edit_tool",
                    "trace_id": trace_id,
                    "query": query,
                    "prompt": prompt,
                    "error_code": "source_image_unavailable",
                    "error": "source image is not available",
                    "report": "Image edit failed: the image to edit is no longer available.",
                }
            resolved_mask = _resolve_image(self.storage, mask_path) if mask_path else None
            if mask_path and resolved_mask is None:
                return {
                    "status": "error",
                    "tool": "image_edit_tool",
                    "trace_id": trace_id,
                    "query": query,
                    "prompt": prompt,
                    "error_code": "mask_unavailable",
                    "error": "mask image is not available",
                    "report": "Image edit failed: the mask image is no longer available.",
                }
            output_dir, keep_last = self.storage.dir("images"), _keep_last(config)
            openai_base_url, api_key, openai_model = _provider_settings(config, self.llm, model)
            # 中文: 同 image_generate_tool——provider 调用与落盘都是同步阻塞操作，
            # 放到工作线程执行以免卡住事件循环。
            binary_images, note = await asyncio.to_thread(
                _run_edit,
                transport=_edit_transport(config),
                base_url=openai_base_url,
                api_key=api_key,
                model=openai_model,
                prompt=prompt,
                image_path=str(resolved_image),
                mask_path=str(resolved_mask) if resolved_mask is not None else None,
                allow_private_download_urls=security_cfg.get("allow_private_download_urls", False) is True,
                max_download_bytes=max(
                    1, _coerce_int(security_cfg.get("max_download_bytes"), _DEFAULT_MAX_DOWNLOAD_BYTES)
                ),
                image_count=image_count,
                size=size,
                timeout_seconds=timeout_seconds,
            )
            image_paths, _ = await asyncio.to_thread(_persist_and_prune, output_dir, binary_images, "edit", keep_last)
            return {
                "status": "success",
                "tool": "image_edit_tool",
                "trace_id": trace_id,
                "query": query,
                "prompt": prompt,
                "source_image": str(resolved_image),
                "model": openai_model,
                "size": size,
                "image_count": len(image_paths),
                "images": image_paths,
                "note": note,
                "report": f"Image edited successfully: {len(image_paths)} file(s).",
            }
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
            return {
                "status": "error",
                "tool": "image_edit_tool",
                "trace_id": trace_id,
                "query": query,
                "prompt": prompt,
                "error_code": _provider_error_code(exc),
                "error": str(exc),
                "report": f"Image edit failed: {exc}",
            }


@plugin_tool(
    "image_prompt_tool",
    tags=("image", "prompt", "offline", "function"),
    allowed_subagents=("image_art_director",),
    metadata={
        "description": "Normalize an image prompt without calling an external provider.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "prompt": {"type": "string"},
                "style": {"type": "string"},
            },
        },
    },
)
async def normalize_image_prompt(payload: dict[str, object]) -> dict[str, object]:
    """Function-decorator example adapted into the standard execute protocol."""
    query = _resolve_query(payload)
    prompt = _extract_prompt(payload, query)
    style = str(payload.get("style", "cinematic")).strip() or "cinematic"
    normalized = " ".join(prompt.split())
    if normalized and style.lower() not in normalized.lower():
        normalized = f"{normalized}, {style} style"
    return {
        "status": "success" if normalized else "error",
        "tool": "image_prompt_tool",
        "prompt": normalized,
        "style": style,
        "offline": True,
        "report": "Image prompt normalized." if normalized else "Image prompt is required.",
    }


class ImagePluginStatusTool:
    """Explicit registration example exposing non-secret plugin configuration."""

    def __init__(self, plugin: Any, runtime_context: dict[str, Any]) -> None:
        self.plugin = plugin
        self.runtime_context = runtime_context

    async def execute(self, payload: dict[str, object]) -> dict[str, object]:
        _ = payload
        config = _plugin_config(self.plugin)
        generation = config.get("generation", {})
        storage = self.runtime_context.get("storage")
        return {
            "status": "success",
            "tool": "image_plugin_status_tool",
            "plugin": self.plugin.name,
            "version": self.plugin.version,
            "provider": generation.get("provider") if isinstance(generation, dict) else None,
            # Where the files live is the host's business; only report whether the
            # storage service this plugin was handed is usable right now.
            "storage_ready": bool(storage is not None and storage.available()),
            "runtime_context_keys": sorted(self.runtime_context),
            "api_key_exposed": False,
            "report": "Image plugin is loaded.",
        }


def register_tools(tool_registry: Any, plugin: Any, runtime_context: dict[str, Any]) -> None:
    """Explicit registration example; decorated tools are discovered afterwards."""
    tool_registry.register(
        ImagePluginStatusTool(plugin, runtime_context),
        name="image_plugin_status_tool",
        tags=("image", "status", "explicit-registration"),
        metadata={
            "description": "Report image plugin status without exposing secrets.",
            "input_schema": {"type": "object", "properties": {}},
        },
    )
