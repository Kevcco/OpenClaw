"""Server-side answer providers for citation-aware knowledge answers."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


class AnswerProviderError(RuntimeError):
    pass


class ExtractiveAnswerProvider:
    """Offline deterministic provider for local demos and tests."""

    def answer(self, question, contexts, history=None):
        if not contexts:
            return "资料中未找到相关内容"
        first = contexts[0]["chunk_text"].strip().replace("\n", " ")
        first = first[:240]
        return f"根据本班材料，{first} [1]"


class HttpAnswerProvider:
    def __init__(self, url, *, api_key=None, timeout=20):
        self.url = url
        self.api_key = api_key
        self.timeout = timeout

    def answer(self, question, contexts, history=None):
        body = json.dumps(
            {
                "question": question,
                "contexts": list(contexts),
                "history": list(history or []),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise AnswerProviderError("answer service unavailable") from error
        answer = payload.get("answer") or payload.get("content")
        if not isinstance(answer, str) or not answer.strip():
            raise AnswerProviderError("answer service returned no answer")
        return answer.strip()


def build_answer_provider(config):
    configured = config.get("ANSWER_PROVIDER")
    if configured is not None and hasattr(configured, "answer"):
        return configured
    if config.get("ANSWER_MODE", "extractive") == "extractive":
        return ExtractiveAnswerProvider()
    url = config.get("ANSWER_API_URL")
    if not url:
        return None
    return HttpAnswerProvider(
        url,
        api_key=config.get("ANSWER_API_KEY"),
        timeout=float(config.get("ANSWER_TIMEOUT", 20)),
    )


def normalize_citations(answer_text, count):
    """Keep only references that point to the returned context list."""
    answer_text = str(answer_text or "").strip()
    references = [int(value) for value in re.findall(r"\[(\d+)\]", answer_text)]
    valid = {value for value in references if 1 <= value <= count}
    answer_text = re.sub(
        r"\[(\d+)\]",
        lambda match: match.group(0) if int(match.group(1)) in valid else "",
        answer_text,
    ).strip()
    if count and not valid:
        answer_text = f"{answer_text} [1]".strip()
    return answer_text, sorted(valid) if valid else ([1] if count else [])
