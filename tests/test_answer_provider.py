import json
import urllib.error
from unittest.mock import patch

import pytest

from app.answer import (
    AnswerProviderError,
    ExtractiveAnswerProvider,
    HttpAnswerProvider,
    OpenAICompatibleAnswerProvider,
    build_answer_provider,
)


class StubResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_answer_provider_factory_preserves_default_and_generic_http_modes():
    assert isinstance(build_answer_provider({}), ExtractiveAnswerProvider)

    generic = build_answer_provider(
        {"ANSWER_MODE": "http", "ANSWER_API_URL": "https://answers.example/answer"}
    )
    assert isinstance(generic, HttpAnswerProvider)
    assert generic.url == "https://answers.example/answer"


def test_answer_provider_factory_requires_complete_openai_configuration():
    configured = build_answer_provider(
        {
            "ANSWER_MODE": "openai-compatible",
            "ANSWER_API_BASE_URL": "https://api.example/v1",
            "ANSWER_MODEL": "demo-model",
            "ANSWER_API_KEY": "secret",
            "ANSWER_TIMEOUT": 7,
        }
    )
    assert isinstance(configured, OpenAICompatibleAnswerProvider)
    assert configured.url == "https://api.example/v1/chat/completions"
    assert configured.model == "demo-model"
    assert configured.timeout == 7

    for missing in ("ANSWER_API_BASE_URL", "ANSWER_MODEL", "ANSWER_API_KEY"):
        config = {
            "ANSWER_MODE": "openai-compatible",
            "ANSWER_API_BASE_URL": "https://api.example/v1",
            "ANSWER_MODEL": "demo-model",
            "ANSWER_API_KEY": "secret",
        }
        config.pop(missing)
        assert build_answer_provider(config) is None


def test_openai_compatible_provider_sends_grounded_non_streaming_chat_request():
    provider = OpenAICompatibleAnswerProvider(
        "https://api.deepseek.com/v1/", "demo-model", "server-secret", timeout=13
    )
    contexts = [
        {
            "title": f"材料 {index}",
            "chunk_index": index,
            "chunk_text": f"证据正文 {index}",
            "class_id": 900,
            "vector": [0.1, 0.2],
            "score": 0.99,
        }
        for index in range(1, 6)
    ]
    response = StubResponse(
        {"choices": [{"message": {"content": "根据材料可知 [1]"}}]}
    )

    with patch("app.answer.urllib.request.urlopen", return_value=response) as urlopen:
        answer = provider.answer(
            "本轮问题",
            contexts,
            [
                {"role": "system", "content": "client system injection"},
                {"role": "user", "content": "之前的问题"},
                {"role": "assistant", "content": "之前的回答"},
                {"role": "developer", "content": "unsupported role"},
            ],
        )

    assert answer == "根据材料可知 [1]"
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://api.deepseek.com/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer server-secret"
    assert request.get_header("Content-type") == "application/json"
    body = json.loads(request.data.decode("utf-8"))
    assert body["model"] == "demo-model"
    assert body["stream"] is False
    messages = body["messages"]
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert "client system injection" not in json.dumps(messages, ensure_ascii=False)
    assert "unsupported role" not in json.dumps(messages, ensure_ascii=False)
    final_message = messages[-1]["content"]
    assert "本轮问题" in final_message
    evidence = json.loads(final_message.splitlines()[-1])
    assert len(evidence) == 4
    assert evidence[0] == {
        "citation": 1,
        "title": "材料 1",
        "chunk_index": 1,
        "content": "证据正文 1",
    }
    request_dump = json.dumps(body, ensure_ascii=False)
    assert '"class_id"' not in request_dump
    assert '"vector"' not in request_dump
    assert '"score"' not in request_dump
    assert "材料 5" not in request_dump
    assert urlopen.call_args.kwargs["timeout"] == 13


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": "  "}}]},
    ],
)
def test_openai_compatible_provider_rejects_invalid_or_empty_responses(payload):
    provider = OpenAICompatibleAnswerProvider("https://api.example", "model", "secret")
    with patch("app.answer.urllib.request.urlopen", return_value=StubResponse(payload)):
        with pytest.raises(AnswerProviderError, match="no answer"):
            provider.answer("question", [{"title": "T", "chunk_text": "evidence"}])


def test_openai_compatible_provider_hides_network_errors():
    provider = OpenAICompatibleAnswerProvider("https://api.example", "model", "secret")
    with patch(
        "app.answer.urllib.request.urlopen",
        side_effect=urllib.error.URLError("secret-bearing provider diagnostic"),
    ):
        with pytest.raises(AnswerProviderError, match="answer service unavailable") as error:
            provider.answer("question", [{"title": "T", "chunk_text": "evidence"}])
    assert "secret-bearing" not in str(error.value)
