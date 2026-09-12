#!/usr/bin/env python3
"""Import each sibling skill's run_audit.run without module-name clashes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

COLLIDING = {
    "http_client",
    "robots_parser",
    "sitemap_sampler",
    "js_shell",
    "jsonld",
    "page_loader",
    "web_search",
    "source_classifier",
    "page_signals",
    "fetch_quality",
    "run_audit",
}


def load_run(scripts_dir: Path) -> ModuleType:
    scripts_dir = Path(scripts_dir)
    for name in COLLIDING:
        sys.modules.pop(name, None)
    path = str(scripts_dir)
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location(
        f"{scripts_dir.parent.name}_run_audit",
        scripts_dir / "run_audit.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {scripts_dir / 'run_audit.py'}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
