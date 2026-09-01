"""调用兼容 OpenAI 的对话接口。"""

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.local_settings import load_local_settings


def load_llm() -> dict[str, str]:
    stored = load_local_settings(get_settings().repo_root).get("llm") or {}
    if not isinstance(stored, dict):
        stored = {}
    return {
        "base_url": str(stored.get("base_url") or "https://api.openai.com/v1").strip(),
        "api_key": str(stored.get("api_key") or "").strip(),
        "model": str(stored.get("model") or "gpt-4o-mini").strip(),
    }


def llm_public() -> dict[str, Any]:
    cfg = load_llm()
    return {
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "has_key": bool(cfg["api_key"]),
    }


def _completions_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def chat_complete(messages: list[dict[str, str]], timeout: float = 90) -> str:
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
    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.post(url, json=payload, headers=headers)
    except Exception as exc:
        raise ValueError(f"AI 请求失败：{exc}") from exc

    if res.status_code >= 400:
        text = res.text[:300]
        raise ValueError(f"AI 接口返回 {res.status_code}：{text}")

    data = res.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise ValueError("AI 返回格式不对") from exc
    return str(content or "").strip()
