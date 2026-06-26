from __future__ import annotations

from pathlib import Path
from typing import Any


class YamlLiteError(ValueError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    return loads_yaml(path.read_text())


def loads_yaml(text: str) -> dict[str, Any]:
    lines = _prepare(text)
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise YamlLiteError(f"Could not parse line: {lines[index][1]}")
    if not isinstance(value, dict):
        raise YamlLiteError("Top-level YAML value must be a mapping")
    return value


def _prepare(text: str) -> list[tuple[int, str]]:
    prepared: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = _strip_comment(raw.rstrip())
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if "\t" in line[:indent]:
            raise YamlLiteError("Tabs are not supported for indentation")
        prepared.append((indent, line.strip()))
    return prepared


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for i, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if i == 0 or line[i - 1].isspace():
                return line[:i].rstrip()
    return line


def _parse_block(
    lines: list[tuple[int, str]], index: int, indent: int
) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, content = lines[index]
    if current_indent < indent:
        return {}, index
    if current_indent != indent:
        raise YamlLiteError(f"Unexpected indentation at line: {content}")
    if content.startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(
    lines: list[tuple[int, str]], index: int, indent: int
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise YamlLiteError(f"Unexpected nested line: {content}")
        if content.startswith("- "):
            break
        key, value = _split_key_value(content)
        if value is None:
            if index + 1 < len(lines) and lines[index + 1][0] > indent:
                result[key], index = _parse_block(lines, index + 1, lines[index + 1][0])
            else:
                result[key] = {}
                index += 1
        else:
            result[key] = _parse_scalar(value)
            index += 1
    return result, index


def _parse_list(
    lines: list[tuple[int, str]], index: int, indent: int
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or not content.startswith("- "):
            break

        item = content[2:].strip()
        if not item:
            if index + 1 < len(lines) and lines[index + 1][0] > indent:
                value, index = _parse_block(lines, index + 1, lines[index + 1][0])
                result.append(value)
            else:
                result.append(None)
                index += 1
            continue

        if _looks_like_mapping_item(item):
            key, value = _split_key_value(item)
            mapping: dict[str, Any] = {key: {} if value is None else _parse_scalar(value)}
            index += 1
            if index < len(lines) and lines[index][0] > indent:
                child, index = _parse_mapping(lines, index, lines[index][0])
                mapping.update(child)
            result.append(mapping)
        else:
            result.append(_parse_scalar(item))
            index += 1
    return result, index


def _looks_like_mapping_item(value: str) -> bool:
    if ":" not in value:
        return False
    before, _sep, _after = value.partition(":")
    return bool(before.strip()) and " " not in before.strip()


def _split_key_value(content: str) -> tuple[str, str | None]:
    if ":" not in content:
        raise YamlLiteError(f"Expected key/value mapping: {content}")
    key, _sep, value = content.partition(":")
    key = key.strip()
    if not key:
        raise YamlLiteError(f"Missing mapping key: {content}")
    value = value.strip()
    return key, value if value else None


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "Null", "~"}:
        return None
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        return value
