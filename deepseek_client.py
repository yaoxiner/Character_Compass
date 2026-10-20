"""DeepSeek Chat Completions SSE 客户端。单次调用、限时、限长、重复熔断。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from novel_core import Route, repeats


class GenerationError(Exception):
    def __init__(self, message: str, *, partial: str = "", usage: dict | None = None,
                 billed_unknown: bool = True):
        super().__init__(message)
        self.partial = partial
        self.usage = usage or {}
        self.billed_unknown = billed_unknown


@dataclass
class GenerationResult:
    content: str
    usage: dict
    finish_reason: str


def generate(api_key: str, base_url: str, route: Route, messages: list[dict],
             *, deadline_seconds: int = 120, json_output: bool = False,
             on_progress: Callable[[str], None] | None = None) -> GenerationResult:
    body = {
        "model": route.model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": route.max_tokens,
        "thinking": {"type": "enabled" if route.thinking else "disabled"},
    }
    if route.effort:
        body["reasoning_effort"] = route.effort
    if json_output:
        body["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    content = ""
    usage = {}
    finish = ""
    checkpoint_length = 0
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            for raw_line in response:
                if time.monotonic() - started > deadline_seconds:
                    raise GenerationError("生成超过时间上限，已中断。", partial=content, usage=usage)
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    raise GenerationError("模型返回了损坏的数据流。", partial=content, usage=usage)
                if event.get("usage"):
                    usage = event["usage"]
                for choice in event.get("choices") or []:
                    delta = choice.get("delta") or {}
                    content += delta.get("content") or ""
                    finish = choice.get("finish_reason") or finish
                if on_progress and len(content) - checkpoint_length >= 500:
                    on_progress(content)
                    checkpoint_length = len(content)
                if len(content) > 26000:
                    raise GenerationError("正文超过本次长度上限，已中断。", partial=content[:26000], usage=usage)
                if repeats(content):
                    raise GenerationError("检测到重复或空白输出，已中断，避免继续消耗 token。",
                                          partial=content, usage=usage)
    except urllib.error.HTTPError as exc:
        raise GenerationError(f"DeepSeek 接口返回 HTTP {exc.code}。请检查 Key、额度或模型名称。",
                              partial=content, usage=usage, billed_unknown=exc.code >= 500) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GenerationError("连接 DeepSeek 失败或长时间无响应。", partial=content, usage=usage) from exc
    if not content.strip():
        raise GenerationError("模型没有返回可用正文。", partial=content, usage=usage)
    if finish not in ("stop", "length"):
        raise GenerationError(f"模型提前结束（{finish or 'unknown'}）。", partial=content, usage=usage)
    return GenerationResult(content, usage, finish)

