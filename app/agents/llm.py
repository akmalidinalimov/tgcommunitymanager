"""One way to ask a model for a structured answer, whoever makes the model.

Every agent here does the same thing: send one prompt, get back a payload that
matches a schema, never free text. The spine stays deterministic precisely
because a model's only job is to fill a shape.

That made the provider an implementation detail from the start, and this module
is where it finally becomes one. Swapping the Replier to another vendor should
be a model id in the environment, not an edit to the Replier.

**Structured output is forced, not requested.** Both vendors can be told they
must call one specific function, and both are. A model that answers in prose
instead is a model whose answer we cannot check, and the grounding gate is the
only thing standing between a guess and 3,326 people.

TLS note: this machine sits behind a TLS-intercepting proxy, so both SDKs are
handed a client wired to the OS trust store rather than building their own. See
`app/net.py`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.net import http_client

log = logging.getLogger("llm")

#: Model families and who serves them. Prefix match, longest first.
PROVIDERS: dict[str, str] = {
    "claude": "anthropic",
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
}


class ProviderError(RuntimeError):
    """The model id names a vendor we cannot reach, or its key is missing."""


def provider_for(model: str) -> str:
    for prefix, name in PROVIDERS.items():
        if model.startswith(prefix):
            return name
    raise ProviderError(
        f"no provider knows how to serve {model!r}. Known prefixes: "
        f"{', '.join(sorted(PROVIDERS))}"
    )


def structured(
    prompt: str,
    *,
    schema: dict,
    model: str,
    anthropic_key: str = "",
    openai_key: str = "",
    max_tokens: int = 1200,
) -> dict[str, Any]:
    """Send one prompt, return the payload the model was forced to produce.

    ``schema`` is the Anthropic tool shape — ``{name, description, input_schema}``
    — because that is what the agents already carry. The OpenAI path translates
    it rather than asking every agent to hold two copies of the same thing.
    """
    which = provider_for(model)
    if which == "anthropic":
        return _anthropic(prompt, schema=schema, model=model,
                          api_key=anthropic_key, max_tokens=max_tokens)
    return _openai(prompt, schema=schema, model=model,
                   api_key=openai_key, max_tokens=max_tokens)


def _anthropic(prompt: str, *, schema: dict, model: str, api_key: str,
               max_tokens: int) -> dict[str, Any]:
    if not api_key:
        raise ProviderError(f"{model} needs ANTHROPIC_API_KEY")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key, http_client=http_client(timeout=120.0))
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[schema],
        tool_choice={"type": "tool", "name": schema["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return dict(block.input)
    raise RuntimeError(f"{model} returned no tool call: {response.content!r}")


def _openai(prompt: str, *, schema: dict, model: str, api_key: str,
            max_tokens: int) -> dict[str, Any]:
    # Checked before the import on purpose. The operator's error should name
    # the variable they forgot, not the package they never installed — and a
    # missing key is the state this project is actually in.
    if not api_key:
        raise ProviderError(f"{model} needs OPENAI_API_KEY")

    import openai

    client = openai.OpenAI(api_key=api_key, http_client=http_client(timeout=120.0))
    tool = {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema.get("description", ""),
            "parameters": schema["input_schema"],
        },
    }
    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=max_tokens,
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": schema["name"]}},
        messages=[{"role": "user", "content": prompt}],
    )
    calls = response.choices[0].message.tool_calls or []
    if not calls:
        raise RuntimeError(f"{model} returned no tool call: {response.choices[0].message!r}")
    # OpenAI hands arguments back as a JSON string; Anthropic hands back a dict.
    # Callers should never have to know which vendor they got.
    return json.loads(calls[0].function.arguments)
