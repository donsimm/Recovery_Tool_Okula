"""GLib.idle_add wiederholt einen Rückruf, solange er True zurückgibt. Ein Timer-Rückruf (gibt True zurück)
darf deshalb nie direkt an idle_add gehen – sonst läuft er pausenlos (früher: NAS-Prüfung, 84 % CPU)."""

import ast
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "okula_recovery"


def _returns_truthy(func: ast.FunctionDef) -> bool:
    for node in ast.walk(func):
        if isinstance(node, (ast.FunctionDef, ast.Lambda)) and node is not func:
            continue
        if isinstance(node, ast.Return) and node.value is not None:
            if not (isinstance(node.value, ast.Constant) and not node.value.value):
                return True
    return False


class IdleCallbackTest(unittest.TestCase):
    def test_no_repeating_idle_callbacks(self):
        problems = []
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text())
            methods: dict[str, ast.FunctionDef] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    methods.setdefault(node.name, node)
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "idle_add" and node.args):
                    continue
                target = node.args[0]
                name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
                func = methods.get(name) if name else None
                if func is not None and _returns_truthy(func):
                    problems.append(f"{path.name}:{node.lineno} idle_add({name}) – {name} gibt True zurück")
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
