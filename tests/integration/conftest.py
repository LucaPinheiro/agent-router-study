from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Integration tests run only when selected with `-m integration`."""
    if "integration" in (config.getoption("markexpr") or ""):
        return
    skip = pytest.mark.skip(reason="needs docker stack: run with -m integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
