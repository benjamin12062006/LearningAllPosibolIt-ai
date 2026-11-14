"""Valida argumentos con el JSON Schema del catálogo y sin resolver URLs."""

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]
from referencing import Registry
from referencing.exceptions import Unresolvable

from ktsu_ai.domain.agent.agent_run import JsonObject

LOCAL_SCHEMAS: Registry[JsonObject] = Registry()


def check_operation_schema(schema: JsonObject) -> None:
    if schema.get("type") != "object":
        raise ValueError("El esquema de argumentos debe describir un objeto.")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise ValueError("Esquema de argumentos inválido.") from None


def validates_arguments(schema: JsonObject, arguments: JsonObject) -> bool:
    try:
        validator = Draft202012Validator(schema, registry=LOCAL_SCHEMAS)
        return bool(validator.is_valid(arguments))
    except Unresolvable:
        return False
