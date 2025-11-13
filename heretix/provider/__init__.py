from __future__ import annotations

import importlib
import pkgutil
from typing import Set

__all__ = ["ensure_adapters_loaded"]

_SKIP_AUTOLOAD: Set[str] = {
    "__init__",
    "base",
    "config",
    "factory",
    "registry",
}
_ADAPTERS_LOADED = False


def ensure_adapters_loaded() -> None:
    """Import provider adapter modules exactly once for side-effect registration."""

    global _ADAPTERS_LOADED
    if _ADAPTERS_LOADED:
        return

    package = __name__
    for module_info in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
        name = module_info.name
        if name.startswith("_") or name in _SKIP_AUTOLOAD:
            continue
        importlib.import_module(f"{package}.{name}")
    _ADAPTERS_LOADED = True
