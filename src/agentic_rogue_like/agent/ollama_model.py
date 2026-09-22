"""A minimal encounter_agent._model()-compatible wrapper around a locally
served Ollama model - lets the game/eval-harness swap Groq for the
fine-tuned local model with a pure configuration change, not a code change.

Lives in the main package (not training/) because it's runtime code: the
fine-tuning pipeline stops at producing a GGUF file, this is what
encounter_agent.py actually talks to once ENCOUNTER_AGENT_MODEL_SOURCE=ollama.
Only needs httpx + pydantic, both already main-package dependencies.

Deliberately does NOT use Ollama's tool-calling/structured-output support:
the fine-tuned model was trained on plain JSON text as the assistant's reply
(see training/data_gen/dataset.py's to_training_record()), not on any
tool-call wire format. Asking Ollama to wrap this in its tool-calling
machinery would be asking the model to do something it was never trained to
do - so this sends a plain chat message and parses/validates the JSON text
response itself, exactly like training did.
"""

from __future__ import annotations

from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

OLLAMA_BASE_URL = "http://localhost:11434"
# The run-2 fine-tune (LoRA on all-linear, loss on completion only): 100%
# schema-valid unconstrained in eval, vs. run 1's 23-36% - see training/RESULTS.md.
DEFAULT_MODEL_NAME = "qwen2.5-enemy-generator-v2"
REQUEST_TIMEOUT_SECONDS = 60.0


class OllamaStructuredOutputError(Exception):
    """Raised when the model's reply isn't valid JSON for the requested schema -
    the same failure mode the encounter agent's retry loop already handles for
    Groq's tool_use_failed errors, just from a different model source."""


class _RawResponse:
    """Minimal stand-in for a LangChain AIMessage - just enough that
    eval/harness.py's cost probe (`result["raw"].usage_metadata`) works
    against this model unmodified. Ollama's own response already reports
    prompt/completion token counts, so this is real data, not a guess."""

    def __init__(self, ollama_response: dict[str, Any]) -> None:
        input_tokens = ollama_response.get("prompt_eval_count", 0)
        output_tokens = ollama_response.get("eval_count", 0)
        self.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }


class _BoundOllamaModel:
    def __init__(
        self,
        model_name: str,
        schema: type[BaseModel],
        include_raw: bool,
        temperature: float | None,
        constrain_output: bool,
    ) -> None:
        self._model_name = model_name
        self._schema = schema
        self._include_raw = include_raw
        self._temperature = temperature
        self._constrain_output = constrain_output

    def invoke(self, prompt: str) -> BaseModel | dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if self._temperature is not None:
            payload["options"] = {"temperature": self._temperature}
        if self._constrain_output:
            # Grammar-constrained decoding: the model can't close the JSON
            # object before every required field is written. Doesn't touch the
            # prompt, so it stays in the format the model was trained on
            # (unlike tool-calling).
            payload["format"] = self._schema.model_json_schema()
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        data = response.json()
        content = data["message"]["content"]

        try:
            parsed = self._schema.model_validate_json(content)
        except Exception as exc:
            raise OllamaStructuredOutputError(
                f"model reply isn't valid {self._schema.__name__} JSON: {content!r}"
            ) from exc

        if not self._include_raw:
            return parsed
        return {"raw": _RawResponse(data), "parsed": parsed, "parsing_error": None}


class OllamaChatModel:
    """Drop-in for the ChatGroq instance encounter_agent._model() returns,
    narrowed to what generate_enemy()/the eval harness actually call:
    with_structured_output(schema, include_raw=...).invoke(prompt)."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        temperature: float | None = None,
        constrain_output: bool = False,
    ) -> None:
        # temperature=None -> use the one baked into the Ollama model's Modelfile.
        self._model_name = model_name
        self._temperature = temperature
        self._constrain_output = constrain_output

    def with_structured_output(
        self, schema: type[BaseModel], include_raw: bool = False
    ) -> _BoundOllamaModel:
        return _BoundOllamaModel(
            self._model_name, schema, include_raw, self._temperature, self._constrain_output
        )
