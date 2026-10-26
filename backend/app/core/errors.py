"""Error types shared by the CLI and (later) the API."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import ValidationError


@dataclass(frozen=True)
class Issue:
    """One validation problem, located by a field path such as ``cases[2].input``."""

    location: str
    message: str

    def __str__(self) -> str:
        return f"{self.location}: {self.message}" if self.location else self.message


class InputValidationError(Exception):
    """Invalid user input (dataset, configuration, gate rules, report file)."""

    def __init__(self, source: str, issues: Iterable[Issue]) -> None:
        self.source = source
        self.issues = list(issues)
        super().__init__(self.format())

    def format(self) -> str:
        lines = [f"{self.source}: {issue}" for issue in self.issues]
        return "\n".join(lines) if lines else f"{self.source}: invalid input"


def format_location(loc: Iterable[int | str], prefix: str = "") -> str:
    """Render a pydantic ``loc`` tuple as ``cases[2].input.question``."""
    out = prefix
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def issues_from_validation_error(exc: ValidationError, prefix: str = "") -> list[Issue]:
    return [
        Issue(location=format_location(err["loc"], prefix), message=err["msg"])
        for err in exc.errors()
    ]
