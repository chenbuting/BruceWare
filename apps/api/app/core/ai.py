"""调用兼容 OpenAI 的对话接口。"""

import ssl
import time
from io import BytesIO
from typing import Any

import httpx
from PIL import Image

from app.core.config import get_settings
from app.core.local_settings import load_local_settings


def _ssl_context() -> ssl.SSLContext:
    """兼容一些中转站不规范的 HTTPS。"""
    ctx = ssl.create_default_context()
    if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
        ctx.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return ctx


def _is_ssl_break(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(word in text for word in ("ssl", "eof", "unexpected_eof", "certificate", "wrong version number"))


def _post(
    url: str,
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    json: Any = None,
    data: Any = None,
    files: Any = None,
) -> httpx.Response:
    last: Exception | None = None
    for verify in (_ssl_context(), False):
        for attempt in range(3):
            try:
                with httpx.Client(timeout=httpx.Timeout(timeout, connect=20), verify=verify, follow_redirects=True) as client:
                    return client.post(url, headers=headers, json=json, data=data, files=files)
            except Exception as exc:
                last = exc
                text = str(exc).lower()
                if "timeout" in text or "timed out" in text:
                    raise ValueError("AI 请求超时。照片太大或接口太慢，请换一张小一点的图再试。") from exc
                if not _is_ssl_break(exc) and attempt == 0:
                    break
                time.sleep(0.8 * (attempt + 1))
    raise ValueError(f"AI 请求失败：{last}") from last


def _shrink_image(data: bytes, max_side: int = 768) -> bytes:
    """压成较小 JPEG，生图少超时。"""
    try:
        image = Image.open(BytesIO(data)).convert("RGB")
        image.thumbnail((max_side, max_side))
        buf = BytesIO()
        image.save(buf, format="JPEG", quality=78)
        return buf.getvalue()
    except Exception:
        return data


def load_llm() -> dict[str, str]:
    stored = load_local_settings(get_settings().repo_root).get("llm") or {}
    if not isinstance(stored, dict):
        stored = {}
    return {
        "base_url": str(stored.get("base_url") or "https://api.openai.com/v1").strip(),
        "api_key": str(stored.get("api_key") or "").strip(),
        "model": str(stored.get("model") or "gpt-4o-mini").strip(),
        "image_base_url": str(stored.get("image_base_url") or "").strip(),
        "image_api_key": str(stored.get("image_api_key") or "").strip(),
        "image_model": str(stored.get("image_model") or "gpt-image-1").strip() or "gpt-image-1",
        "embedding_model": str(stored.get("embedding_model") or "text-embedding-3-small").strip()
        or "text-embedding-3-small",
    }


def llm_public() -> dict[str, Any]:
    cfg = load_llm()
    return {
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "image_base_url": cfg.get("image_base_url") or "",
        "image_model": cfg.get("image_model") or "gpt-image-1",
        "has_key": bool(cfg["api_key"]),
        "has_image_key": bool(cfg.get("image_api_key")),
    }


def _image_auth() -> tuple[str, str, str]:
    """生图用自己的地址和 Key；没填就退回对话那套。"""
    cfg = load_llm()
    key = cfg.get("image_api_key") or cfg["api_key"]
    if not key:
        raise ValueError("请先在设置里填写生图 Key，或填写对话 Key")
    return cfg.get("image_base_url") or cfg["base_url"], key, cfg.get("image_model") or "gpt-image-1"


def _embeddings_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.endswith("/embeddings"):
        return url
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    if url.endswith("/v1"):
        return f"{url}/embeddings"
    return f"{url}/v1/embeddings"


def embedding_profile() -> str:
    """当前向量模型名，搬家时对得上才不用重算。"""

    return load_llm().get("embedding_model") or "text-embedding-3-small"


def embed_texts(texts: list[str], timeout: float = 60) -> list[list[float]]:
    """把几段文字变成向量。接口不支持就抛错，调用方退回关键词。"""

    cleaned = [item.strip() for item in texts if (item or "").strip()]
    if not cleaned:
        return []
    cfg = load_llm()
    if not cfg["api_key"]:
        raise ValueError("请先在设置里填写 AI Key")
    url = _embeddings_url(cfg["base_url"])
    payload = {"model": cfg.get("embedding_model") or "text-embedding-3-small", "input": cleaned}
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    res = _post(url, timeout=timeout, json=payload, headers=headers)
    if res.status_code >= 400:
        raise ValueError(f"向量接口返回 {res.status_code}：{res.text[:300]}")
    data = res.json()
    try:
        items = sorted(data["data"], key=lambda item: int(item.get("index") or 0))
        return [list(item["embedding"]) for item in items]
    except Exception as exc:
        raise ValueError("向量接口返回格式不对") from exc


def _completions_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def chat_complete(messages: list[dict[str, Any]], timeout: float = 90) -> str:
    """发一轮对话，返回助手文字。"""

    cfg = load_llm()
    if not cfg["api_key"]:
        raise ValueError("请先在设置里填写 AI Key")
    if not cfg["model"]:
        raise ValueError("请先在设置里填写模型名")

    url = _completions_url(cfg["base_url"])
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.6,
    }
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    res = _post(url, timeout=timeout, json=payload, headers=headers)
    if res.status_code >= 400:
        text = res.text[:300]
        raise ValueError(f"AI 接口返回 {res.status_code}：{text}")

    data = res.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise ValueError("AI 返回格式不对") from exc
    return str(content or "").strip()


def _images_root(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    if url.endswith("/v1"):
        return url
    return f"{url}/v1"


def image_edit(
    prompt: str,
    images: list[bytes],
    size: str = "1024x1024",
    timeout: float = 180,
    sizes: list[str] | None = None,
    qualities: list[str] | None = None,
) -> bytes:
    """按参考图改图 / 生图，走兼容 OpenAI 的 images 接口。"""

    base_url, api_key, model = _image_auth()
    root = _images_root(base_url)
    headers = {"Authorization": f"Bearer {api_key}"}
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for index, raw in enumerate(images[:5]):
        files.append(("image[]", (f"ref-{index + 1}.jpg", _shrink_image(raw), "image/jpeg")))
    size_list: list[str] = []
    for item in (*(sizes or []), size, "1024x1024"):
        if item and item not in size_list:
            size_list.append(item)
    quality_list = [item for item in (qualities or []) if item] + [""]
    last_error = ""
    for current in size_list:
        stop_sizes = False
        for quality in quality_list:
            data = {"model": model, "prompt": prompt, "size": current, "response_format": "b64_json"}
            if quality:
                data["quality"] = quality
            try:
                res = _post(f"{root}/images/edits", timeout=timeout, data=data, files=files, headers=headers)
            except Exception as exc:
                last_error = str(exc)
                continue
            if res.status_code < 400:
                return _read_image_bytes(res.json())
            last_error = res.text[:300]
            if res.status_code != 400:
                stop_sizes = True
                break
        if stop_sizes:
            break
    files_single = [("image", (name, blob, mime)) for _, (name, blob, mime) in files]
    data = {"model": model, "prompt": prompt, "size": "1024x1024", "response_format": "b64_json"}
    try:
        res = _post(f"{root}/images/edits", timeout=timeout, data=data, files=files_single, headers=headers)
        if res.status_code < 400:
            return _read_image_bytes(res.json())
        last_error = res.text[:300]
    except Exception as exc:
        last_error = str(exc)
    raise ValueError(f"生图失败：{last_error or '接口不可用'}。请再试一次，或先关掉风格少传几张图。")


def image_generate(prompt: str, size: str = "1024x1024", timeout: float = 120) -> bytes:
    """只按文字生图。"""

    base_url, api_key, model = _image_auth()
    root = _images_root(base_url)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "prompt": prompt, "size": size, "response_format": "b64_json", "n": 1}
    res = _post(f"{root}/images/generations", timeout=timeout, json=payload, headers=headers)
    if res.status_code >= 400:
        raise ValueError(f"生图失败：{res.text[:300]}")
    return _read_image_bytes(res.json())


def _read_image_bytes(data: dict[str, Any]) -> bytes:
    import base64

    try:
        item = data["data"][0]
    except Exception as exc:
        raise ValueError("生图返回格式不对") from exc
    encoded = item.get("b64_json")
    if encoded:
        return base64.b64decode(encoded)
    url = item.get("url")
    if url:
        with httpx.Client(timeout=60) as client:
            res = client.get(url)
        if res.status_code >= 400:
            raise ValueError("生图下载失败")
        return res.content
    raise ValueError("生图没有返回图片")
