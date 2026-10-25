"""Tests that the codebase stays documented and the docs stay honest."""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _undocumented(path):
    """Return the names of definitions in a file that lack docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing = []
    if not ast.get_docstring(tree):
        missing.append("<module>")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and not ast.get_docstring(node):
            missing.append(f"{node.name} (line {node.lineno})")
    return missing


def test_every_module_class_and_function_has_a_docstring():
    """Every module, class, and function in madd/ and tests/ is documented."""
    offenders = {}
    for base in (ROOT / "madd", ROOT / "tests"):
        for path in sorted(base.glob("*.py")):
            missing = _undocumented(path)
            if missing:
                offenders[str(path.relative_to(ROOT))] = missing
    assert offenders == {}, f"undocumented definitions: {offenders}"


def test_readme_module_map_lists_every_package_module():
    """The README repository layout names every module in madd/."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [path.name for path in sorted((ROOT / "madd").glob("*.py"))
               if path.name not in readme]
    assert missing == [], f"modules missing from the README layout: {missing}"
