"""Collection guards for GUI tests that need flet installed."""

import importlib.util

collect_ignore = []

if importlib.util.find_spec("flet") is None:
    collect_ignore = ["test_workspace_demo.py"]
