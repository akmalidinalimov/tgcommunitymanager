"""The provider seam.

The Replier's model became an environment variable because the founders judge
Uzbek quality by reading replies, and that judgement should not need a code
change. What these tests protect is the part that is easy to get silently wrong:
the two vendors disagree about the shape of a tool, about how arguments come
back, and about which key is required — and a caller must never have to know.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from app.agents.llm import PROVIDERS, ProviderError, provider_for, structured

SCHEMA = {
    "name": "submit_reply",
    "description": "Submit a drafted comment reply.",
    "input_schema": {
        "type": "object",
        "properties": {"action": {"type": "string"}, "draft": {"type": "string"}},
        "required": ["action", "draft"],
    },
}


class TestRouting:
    def test_claude_ids_go_to_anthropic(self):
        assert provider_for("claude-opus-5") == "anthropic"
        assert provider_for("claude-haiku-4-5-20251001") == "anthropic"

    def test_gpt_ids_go_to_openai(self):
        assert provider_for("gpt-5.6-luna") == "openai"
        assert provider_for("gpt-5.6-sol") == "openai"

    def test_an_unknown_family_refuses_rather_than_guessing(self):
        # A typo'd REPLY_MODEL must fail loudly at the first reply, not fall
        # through to a default vendor and quietly bill the wrong account.
        with pytest.raises(ProviderError) as exc:
            provider_for("llama-3-70b")
        assert "llama-3-70b" in str(exc.value)

    def test_every_declared_prefix_resolves(self):
        for prefix in PROVIDERS:
            assert provider_for(f"{prefix}-something") in {"anthropic", "openai"}


class TestMissingKeys:
    """Each vendor names the variable the operator has to set."""

    def test_anthropic_without_its_key(self):
        with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
            structured("hi", schema=SCHEMA, model="claude-opus-5", anthropic_key="")

    def test_openai_without_its_key(self):
        # Not an ImportError: the key is checked before the SDK is imported, so
        # this is the message a founder sees when they set REPLY_MODEL and
        # forget the key — which is exactly the state the project is in.
        with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
            structured("hi", schema=SCHEMA, model="gpt-5.6-luna", openai_key="")

    def test_a_present_anthropic_key_does_not_satisfy_openai(self):
        with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
            structured("hi", schema=SCHEMA, model="gpt-5.6-luna",
                       anthropic_key="sk-ant-real", openai_key="")


# --- fakes, so the translation is provable without a network or an account ---

class _FakeCompletions:
    def __init__(self, sink: dict, arguments: str):
        self.sink, self.arguments = sink, arguments

    def create(self, **kwargs):
        self.sink.update(kwargs)
        call = types.SimpleNamespace(
            function=types.SimpleNamespace(name="submit_reply", arguments=self.arguments)
        )
        message = types.SimpleNamespace(tool_calls=[call])
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


DEFAULT_ARGS = json.dumps({"action": "reply", "draft": "Bepul versiyasi bor"})


def _install_fake_openai(monkeypatch, sink: dict, arguments: str = DEFAULT_ARGS):
    module = types.ModuleType("openai")

    class OpenAI:
        def __init__(self, **_):
            self.chat = types.SimpleNamespace(completions=_FakeCompletions(sink, arguments))

    module.OpenAI = OpenAI
    monkeypatch.setitem(sys.modules, "openai", module)


class TestOpenAITranslation:
    """The agents hold one schema, in Anthropic's shape. This is the adapter."""

    def test_the_anthropic_tool_shape_becomes_an_openai_function(self, monkeypatch):
        sent: dict = {}
        _install_fake_openai(monkeypatch, sent)
        structured("hi", schema=SCHEMA, model="gpt-5.6-luna", openai_key="sk-test")

        tool = sent["tools"][0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "submit_reply"
        # input_schema -> parameters. Same object, different key: this rename is
        # the whole reason the adapter exists.
        assert tool["function"]["parameters"] == SCHEMA["input_schema"]

    def test_the_tool_call_is_forced_not_offered(self, monkeypatch):
        # A model that answers in prose is a model whose answer the grounding
        # gate cannot inspect. Both vendors must be compelled, not asked.
        sent: dict = {}
        _install_fake_openai(monkeypatch, sent)
        structured("hi", schema=SCHEMA, model="gpt-5.6-luna", openai_key="sk-test")
        assert sent["tool_choice"] == {
            "type": "function", "function": {"name": "submit_reply"},
        }

    def test_arguments_come_back_as_a_dict_like_anthropic(self, monkeypatch):
        # OpenAI returns a JSON *string*; Anthropic returns a dict. draft_reply
        # calls .get() on whatever it receives, so the string must never escape.
        _install_fake_openai(monkeypatch, {})
        payload = structured("hi", schema=SCHEMA, model="gpt-5.6-luna", openai_key="sk-test")
        assert isinstance(payload, dict)
        assert payload["draft"] == "Bepul versiyasi bor"

    def test_no_tool_call_raises_rather_than_returning_empty(self, monkeypatch):
        # The shape of every bug this project has had: a failure that looks like
        # a success. An empty payload would become action="escalate" by default
        # and read as a deliberate decision.
        module = types.ModuleType("openai")

        class OpenAI:
            def __init__(self, **_):
                message = types.SimpleNamespace(tool_calls=None)
                self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(
                    create=lambda **_kw: types.SimpleNamespace(
                        choices=[types.SimpleNamespace(message=message)])
                ))

        module.OpenAI = OpenAI
        monkeypatch.setitem(sys.modules, "openai", module)
        with pytest.raises(RuntimeError, match="no tool call"):
            structured("hi", schema=SCHEMA, model="gpt-5.6-luna", openai_key="sk-test")


class TestReplierUsesTheSeam:
    """draft_reply must be vendor-blind: same Draft out of either provider."""

    def test_a_gpt_draft_is_normalized_like_a_claude_one(self, monkeypatch):
        from app.agents.context import ReplyContext, ThreadMessage
        from app.telegram.classifier import Kind
        from app.agents.replier import draft_reply
        from app.text.script import Script

        # Apostrophes typed the easy way must still publish as okina/tutuq. The
        # normalizer lives in draft_reply, above the provider, so switching
        # vendors cannot quietly drop it.
        _install_fake_openai(
            monkeypatch, {},
            arguments=json.dumps({"action": "reply", "draft": "To'g'ri, sun'iy",
                                  "grounded_on": [], "reasoning": "x"}),
        )
        ctx = ReplyContext(
            post_text="post",
            target=ThreadMessage(message_id=5, author="Aziz", author_id=42,
                                 text="bepulmi?", kind=Kind.HUMAN),
            thread_root_id=1, history=[], script=Script.LATIN,
        )
        draft = draft_reply(ctx, api_key="", openai_key="sk-test", model="gpt-5.6-luna")
        assert draft.is_reply
        assert draft.draft == "Toʻgʻri, sunʼiy"

    def test_the_model_argument_is_what_selects_the_vendor(self, monkeypatch):
        from app.agents.context import ReplyContext, ThreadMessage
        from app.telegram.classifier import Kind
        from app.agents.replier import draft_reply
        from app.text.script import Script

        ctx = ReplyContext(
            post_text="post",
            target=ThreadMessage(message_id=5, author="Aziz", author_id=42,
                                 text="bepulmi?", kind=Kind.HUMAN),
            thread_root_id=1, history=[], script=Script.LATIN,
        )
        # No anthropic key, no openai key, gpt model -> it must complain about
        # the OpenAI key, proving the model id and not a hardcoded constant
        # picked the path.
        with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
            draft_reply(ctx, api_key="", openai_key="", model="gpt-5.6-luna")
