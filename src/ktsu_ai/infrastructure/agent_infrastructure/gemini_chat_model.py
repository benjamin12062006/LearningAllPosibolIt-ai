"""Gemini por Vertex AI como modelo del agente (plan 03 del agente, G3 a G5).

Credenciales de la cuenta (ADC) en local y la cuenta de servicio en Cloud Run:
sin clave de API, igual que los embeddings.
"""

from collections.abc import Sequence
from typing import Any, Final

from google.auth.credentials import Credentials
from google.genai import types
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.llms.function_calling import FunctionCallingLLM
from llama_index.core.tools.types import BaseTool
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.llms.google_genai.base import VertexAIConfig

from ktsu_ai.config.configuration import ChatModelConfiguration

# Dato de la ficha del modelo (ficha 03, F1). Darlo, junto con `max_tokens`, evita
# que el conector pregunte a Google al crearse con una llamada síncrona (E2).
GEMINI_CONTEXT_WINDOW: Final = 1_048_576


def create_gemini_chat_model(
    config: ChatModelConfiguration, credentials: Credentials | None = None
) -> FunctionCallingLLM:
    """Sin `credentials`, las de la cuenta (ADC). Las pruebas pasan unas anónimas."""
    return CatalogSchemaGemini(
        model=config.model,
        vertexai_config=VertexAIConfig(
            credentials=credentials,
            project=config.google_cloud_project,
            location=config.location,
        ),
        context_window=GEMINI_CONTEXT_WINDOW,
        max_tokens=config.max_output_tokens,
        http_options=types.HttpOptions(timeout=config.timeout_seconds * 1000),
        # Con una configuración propia, el conector ya no pone `max_output_tokens`.
        generation_config=types.GenerateContentConfig(
            max_output_tokens=config.max_output_tokens,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel(config.thinking_level)
            ),
        ),
    )


class CatalogSchemaGemini(GoogleGenAI):
    """Gemini con el JSON Schema de cada herramienta tal cual lo manda Nest.

    El conector convierte el esquema al `Schema` de Google, que rechaza palabras
    clave válidas como `uniqueItems` (ficha 03, E4). `parameters_json_schema` lo
    manda completo y Gemini lo respeta (E5). Mensajes, llamadas y firmas de
    razonamiento siguen siendo cosa del conector.
    """

    def _prepare_chat_with_tools(
        self,
        tools: Sequence[BaseTool],
        user_msg: str | ChatMessage | None = None,
        chat_history: list[ChatMessage] | None = None,
        verbose: bool = False,
        allow_parallel_tool_calls: bool = False,
        tool_required: bool = False,
        tool_choice: str | dict[str, Any] | None = None,
        strict: bool | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        # Sin herramientas, el conector solo prepara los mensajes y el modo de llamada.
        params = super()._prepare_chat_with_tools(
            [],
            user_msg,
            chat_history,
            verbose,
            allow_parallel_tool_calls,
            tool_required,
            tool_choice,
            strict,
            **kwargs,
        )
        if tools:
            declarations = [_declaration(tool) for tool in tools]
            params["tools"] = [types.Tool(function_declarations=declarations)]
        _restore_allowed_names(params["tool_config"], tools, tool_choice)
        return params


def _declaration(tool: BaseTool) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=tool.metadata.get_name(),
        description=tool.metadata.description,
        parameters_json_schema=tool.metadata.get_parameters_dict(),
    )


def _restore_allowed_names(
    tool_config: types.ToolConfig,
    tools: Sequence[BaseTool],
    tool_choice: str | dict[str, Any] | None,
) -> None:
    """Con una herramienta obligatoria, el conector limita los nombres permitidos.

    Como se le pasó una lista vacía, la deja vacía; aquí se rellena con los
    nombres reales.
    """
    calling = tool_config.function_calling_config
    if calling is None or calling.allowed_function_names is None:
        return
    names = [tool.metadata.get_name() for tool in tools]
    calling.allowed_function_names = [tool_choice] if tool_choice in names else names
