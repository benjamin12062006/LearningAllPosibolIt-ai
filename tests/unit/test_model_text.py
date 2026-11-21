"""Datos para el modelo: separar listas anidadas sin perder nada y codificar en TOON."""

import copy

import toon_format

from ktsu_ai.application.agent_application.model_text import (
    separate_nested_lists,
    to_model_text,
)
from ktsu_ai.domain.agent.agent_run import JsonValue

PAGE: JsonValue = {
    "items": [
        {"rowId": "r1", "values": {"c1": "SKU-1", "c2": 10.5}, "problems": []},
        {
            "rowId": "r2",
            "values": {"c1": "SKU-2", "c2": None},
            "problems": [{"columnId": "c2", "code": "REQUIRED"}],
        },
    ],
    "nextCursor": None,
}


def test_rows_become_a_table_and_their_problems_a_sibling_table() -> None:
    assert separate_nested_lists(PAGE) == {
        "items": [
            {"rowId": "r1", "values": {"c1": "SKU-1", "c2": 10.5}},
            {"rowId": "r2", "values": {"c1": "SKU-2", "c2": None}},
        ],
        "nextCursor": None,
        "items.problems": [{"rowId": "r2", "columnId": "c2", "code": "REQUIRED"}],
    }
    text = to_model_text(PAGE)
    assert "items[2]{rowId,values{c1,c2}}:" in text
    assert "items.problems[1]{rowId,columnId,code}:" in text


def test_nothing_is_lost_the_original_can_be_rebuilt() -> None:
    separated = separate_nested_lists(PAGE)
    assert isinstance(separated, dict)

    rebuilt = rebuild(separated, "items", "problems", "rowId")

    assert rebuilt == PAGE


def test_empty_lists_in_every_row_become_one_empty_table() -> None:
    page: JsonValue = {"items": [{"rowId": "r1", "problems": []}]}

    assert separate_nested_lists(page) == {
        "items": [{"rowId": "r1"}],
        "items.problems": [],
    }


def test_the_received_value_does_not_change() -> None:
    before = copy.deepcopy(PAGE)

    to_model_text(PAGE)

    assert before == PAGE


def test_lists_that_cannot_be_rebuilt_stay_in_place() -> None:
    without_parent: JsonValue = {"items": [{"name": "a", "tags": [{"t": 1}]}]}
    with_primitives: JsonValue = {"items": [{"id": "a", "tags": ["x", "y"]}]}
    parent_key_inside: JsonValue = {"items": [{"id": "a", "sub": [{"id": "b"}]}]}
    boolean_parent: JsonValue = {"items": [{"id": True, "sub": [{"x": 1}]}]}

    for value in (without_parent, with_primitives, parent_key_inside, boolean_parent):
        assert separate_nested_lists(value) == value


def test_an_existing_key_with_the_sibling_name_is_kept() -> None:
    value: JsonValue = {
        "items": [{"id": "a", "sub": [{"x": 1}]}],
        "items.sub": "ya estaba",
    }

    assert separate_nested_lists(value) == value


def test_nested_levels_are_separated_too() -> None:
    value: JsonValue = {
        "result": {"items": [{"id": "a", "sub": [{"x": 1}, {"x": 2}]}]},
    }

    assert separate_nested_lists(value) == {
        "result": {
            "items": [{"id": "a"}],
            "items.sub": [{"id": "a", "x": 1}, {"id": "a", "x": 2}],
        }
    }


def test_the_text_is_valid_toon() -> None:
    separated = separate_nested_lists(PAGE)

    assert toon_format.loads(to_model_text(PAGE)) == separated


def rebuild(
    separated: dict[str, JsonValue], key: str, field: str, parent: str
) -> dict[str, JsonValue]:
    """La operación inversa: vuelve a meter cada hija en su fila."""
    rows = separated[key]
    children = separated[f"{key}.{field}"]
    assert isinstance(rows, list) and isinstance(children, list)
    rebuilt_rows: list[JsonValue] = []
    for row in rows:
        assert isinstance(row, dict)
        own = [
            {name: value for name, value in child.items() if name != parent}
            for child in children
            if isinstance(child, dict) and child[parent] == row[parent]
        ]
        rebuilt_rows.append({**row, field: own})
    rebuilt = {
        name: value for name, value in separated.items() if name != f"{key}.{field}"
    }
    rebuilt[key] = rebuilt_rows
    return rebuilt
