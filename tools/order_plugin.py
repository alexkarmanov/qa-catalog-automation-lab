"""Optional pytest plugin that changes the collection order to prove order independence.

``KQA_ORDER=reverse`` reverses the collected tests; ``KQA_ORDER=shuffle:<seed>`` shuffles them deterministically.
Load with: ``python -m pytest -p tools.order_plugin``.
"""
from __future__ import annotations

import os
import random
from typing import List

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    mode = os.environ.get("KQA_ORDER", "")
    if mode == "reverse":
        items.reverse()
    elif mode.startswith("shuffle:"):
        random.Random(int(mode.split(":", 1)[1])).shuffle(items)
