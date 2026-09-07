from __future__ import annotations

import importlib.util
import platform
import sys


def environment_diagnostics() -> dict:
    optional = {
        "CoolProp": importlib.util.find_spec("CoolProp") is not None,
        "FastAPI": importlib.util.find_spec("fastapi") is not None,
    }

    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "optional_packages": optional,
        "coolprop_mode": (
            "Available for supported pure-fluid properties"
            if optional["CoolProp"]
            else "Not installed - internal property fallback remains active"
        ),
    }
