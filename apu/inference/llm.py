"""Which model answers which role, and through which provider.

Four places in the pipeline call a language model, and they are not the same job:

  tutor        answers the pupil, and must make native tool calls (web search, notebook)
  extraction   turns one exchange into the JSON the memory write-back stores
  query gate   decides whether a search query is school use
  guard        classifies the pupil's message (called through NeMo Guardrails, not here)

Each one is configured independently, because measuring them separately showed that no
single model wins everywhere: the best guard is a small model that cannot call tools, and
the model that writes the best answers is four times slower at returning a JSON object.
See docs/models.md for the numbers behind the defaults.

Every provider here speaks the OpenAI chat completions API, Gemini included through its
compatibility endpoint, so the agent's code does not change when a role moves. Clients are
built on first use: a device without a key for some role must still start and run the roles
it can.
"""

import os

from openai import OpenAI

from apu import config

# provider -> (base URL, the environment variable holding its key)
PROVIDERS = {
    "nebius": (config.NEBIUS_BASE_URL, "NEBIUS_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
}

_clients: dict[str, OpenAI] = {}


class ProviderKeyMissing(RuntimeError):
    """A role was called and its provider has no key."""


def get_client(provider: str) -> OpenAI:
    """The client for one provider, built on first use."""
    if provider not in _clients:
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider {provider!r}; one of: {', '.join(PROVIDERS)}")
        base_url, key_variable = PROVIDERS[provider]
        api_key = os.environ.get(key_variable)
        if not api_key:
            raise ProviderKeyMissing(
                f"{key_variable} is not set, and it is needed for the {provider} models. "
                "Add it to your .env file."
            )
        _clients[provider] = OpenAI(base_url=base_url, api_key=api_key)
    return _clients[provider]


def set_client(client, provider: str | None = None) -> None:
    """Swap a client, for tests and for a device that builds its own. None clears them all."""
    if client is None:
        _clients.clear()
        return
    for name in ([provider] if provider else PROVIDERS):
        _clients[name] = client


def _complete(provider: str, model: str, messages: list[dict], **kwargs):
    return get_client(provider).chat.completions.create(
        model=kwargs.pop("model", model), messages=messages, **kwargs)


def call_main_model(messages: list[dict], **kwargs) -> str:
    """The answer the pupil reads."""
    response = _complete(config.MAIN_PROVIDER, config.MAIN_MODEL, messages, **kwargs)
    return response.choices[0].message.content


def call_main_model_message(messages: list[dict], **kwargs):
    """The answer call, returning the whole message rather than only its text.

    Needed for native tool calling: when the model asks for a tool, `content` is None and the
    request sits in `tool_calls`, which call_main_model would drop.
    """
    response = _complete(config.MAIN_PROVIDER, config.MAIN_MODEL, messages, **kwargs)
    return response.choices[0].message


def call_extraction_model(messages: list[dict], **kwargs) -> str:
    """The memory write-back, off the critical path of what the pupil reads."""
    response = _complete(config.EXTRACTION_PROVIDER, config.EXTRACTION_MODEL, messages, **kwargs)
    return response.choices[0].message.content


def call_query_gate_model(messages: list[dict], **kwargs) -> str:
    """The second gate: is this search query school use?"""
    response = _complete(config.QUERY_GATE_PROVIDER, config.QUERY_GATE_MODEL, messages, **kwargs)
    return response.choices[0].message.content
