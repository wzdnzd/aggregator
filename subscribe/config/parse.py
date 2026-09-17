# -*- coding: utf-8 -*-

from __future__ import annotations

import re
from typing import Iterator

import utils


class ParseError(ValueError):
    def __init__(self, message: str, location: str = "") -> None:
        self.location = location
        text = f"{location}: {message}" if location else message
        super().__init__(text)


def join_location(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]" if parent else f"[{key}]"
    return f"{parent}.{key}" if parent else key


class Node:
    def __init__(self, value: object, location: str = "") -> None:
        self.value = value
        self.location = location

    @property
    def absent(self) -> bool:
        return self.value is None

    def fail(self, message: str) -> None:
        raise ParseError(message, self.location)

    def object(self) -> ObjectNode:
        if not isinstance(self.value, dict):
            self.fail("must be an object")
        return ObjectNode(self.value, self.location)

    def array(self) -> ArrayNode:
        if not isinstance(self.value, list):
            self.fail("must be an array")
        return ArrayNode(self.value, self.location)


class ObjectNode:
    def __init__(self, data: dict[str, object], location: str = "") -> None:
        self._data = data
        self.location = location

    def has(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> list[str]:
        return list(self._data.keys())

    def field(self, key: str) -> Node:
        location = join_location(self.location, key)
        if key not in self._data:
            return Node(None, location)
        return Node(self._data[key], location)

    def rest(self, known: set[str]) -> dict[str, object]:
        return {key: value for key, value in self._data.items() if key not in known}

    def boolean(self, key: str, default: bool | None = None, required: bool = False) -> bool | None:
        node = self.field(key)
        if node.absent:
            if required:
                node.fail("is required")
            return default
        if not isinstance(node.value, bool):
            node.fail("must be a boolean")
        return node.value

    def integer(
        self,
        key: str,
        default: int | None = None,
        required: bool = False,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int | None:
        node = self.field(key)
        if node.absent:
            if required:
                node.fail("is required")
            return default
        if isinstance(node.value, bool) or not isinstance(node.value, int):
            node.fail("must be an integer")
        if minimum is not None and node.value < minimum:
            node.fail(f"must be >= {minimum}")
        if maximum is not None and node.value > maximum:
            node.fail(f"must be <= {maximum}")
        return node.value

    def number(
        self,
        key: str,
        default: float | None = None,
        required: bool = False,
        minimum: float | None = None,
    ) -> float | None:
        node = self.field(key)
        if node.absent:
            if required:
                node.fail("is required")
            return default
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            node.fail("must be a number")
        value = float(node.value)
        if minimum is not None and value < minimum:
            node.fail(f"must be >= {minimum}")
        return value

    def string(
        self,
        key: str,
        default: str | None = None,
        required: bool = False,
        allow_empty: bool = True,
    ) -> str | None:
        node = self.field(key)
        if node.absent:
            if required:
                node.fail("is required")
            return default
        if not isinstance(node.value, str):
            node.fail("must be a string")
        value = utils.trim(node.value)
        if not allow_empty and not value:
            node.fail("must not be empty")
        return value

    def string_list(self, key: str, default: list[str] | None = None, unique: bool = True) -> list[str]:
        node = self.field(key)
        if node.absent:
            return [] if default is None else list(default)
        if not isinstance(node.value, list):
            node.fail("must be an array")
        items = []
        for index, item in enumerate(node.value):
            if not isinstance(item, str):
                Node(item, join_location(node.location, index)).fail("must be a string")
            text = utils.trim(item)
            if text:
                items.append(text)
        return list(dict.fromkeys(items)) if unique else items

    def string_or_list(self, key: str, default: str | list[str] = "") -> str | list[str]:
        node = self.field(key)
        if node.absent:
            return default
        if isinstance(node.value, str):
            return utils.trim(node.value)
        if isinstance(node.value, list):
            items = []
            for index, item in enumerate(node.value):
                if not isinstance(item, str):
                    Node(item, join_location(node.location, index)).fail("must be a string")
                text = utils.trim(item)
                if text:
                    items.append(text)
            return items
        node.fail("must be a string or array")

    def regex(self, key: str, default: str = "") -> str:
        text = self.string(key, default=default) or ""
        if not text:
            return ""
        try:
            re.compile(text)
        except re.error as exc:
            self.field(key).fail(f"is not a valid regex: {exc}")
        return text


class ArrayNode:
    def __init__(self, items: list[object], location: str = "") -> None:
        self._items = items
        self.location = location

    def __iter__(self) -> Iterator[Node]:
        for index, item in enumerate(self._items):
            yield Node(item, join_location(self.location, index))

    def __len__(self) -> int:
        return len(self._items)
