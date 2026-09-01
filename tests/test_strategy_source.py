"""Dependency-free structural checks for the strategy source files."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STRATEGIES = {
    "VibeRsiStrategy.py": "VibeRsiStrategy",
    "KoreanStarterStrategy.py": "KoreanStarterStrategy",
    "MultiTimeframeAtrStrategy.py": "MultiTimeframeAtrStrategy",
}
VERIFIED_STARTUP_COUNTS = {
    "VibeRsiStrategy": 199,
    "KoreanStarterStrategy": 799,
    "MultiTimeframeAtrStrategy": 799,
}
REQUIRED_METHODS = {
    "populate_indicators",
    "populate_entry_trend",
    "populate_exit_trend",
}


def class_assignments(node: ast.ClassDef) -> dict[str, object]:
    values: dict[str, object] = {}
    for statement in node.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(statement.value)
                except (TypeError, ValueError):
                    pass
    return values


class StrategySourceTests(unittest.TestCase):
    def strategy_class(self, filename: str, class_name: str) -> tuple[ast.Module, ast.ClassDef]:
        path = ROOT / "strategies" / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        strategy = next(
            (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name),
            None,
        )
        self.assertIsNotNone(strategy, f"{class_name} class is missing")
        return tree, strategy  # type: ignore[return-value]

    def test_strategy_contracts(self) -> None:
        for filename, class_name in STRATEGIES.items():
            with self.subTest(strategy=class_name):
                _, strategy = self.strategy_class(filename, class_name)
                assignments = class_assignments(strategy)
                methods = {
                    node.name for node in strategy.body if isinstance(node, ast.FunctionDef)
                }

                self.assertEqual(assignments.get("INTERFACE_VERSION"), 3)
                self.assertFalse(assignments.get("can_short"))
                self.assertTrue(assignments.get("process_only_new_candles"))
                self.assertTrue(REQUIRED_METHODS.issubset(methods))

    def test_startup_count_covers_longest_indicator_period(self) -> None:
        for filename, class_name in STRATEGIES.items():
            with self.subTest(strategy=class_name):
                tree, strategy = self.strategy_class(filename, class_name)
                assignments = class_assignments(strategy)
                periods = [
                    keyword.value.value
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    for keyword in node.keywords
                    if keyword.arg == "timeperiod"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, int)
                ]
                self.assertGreaterEqual(
                    assignments["startup_candle_count"],
                    max(periods),
                    "startup_candle_count must at least cover the longest indicator period",
                )
                self.assertEqual(
                    assignments["startup_candle_count"],
                    VERIFIED_STARTUP_COUNTS[class_name],
                    "startup count must match the verified recursive-analysis result",
                )

    def test_no_explicit_future_shift_or_positional_access(self) -> None:
        for filename, class_name in STRATEGIES.items():
            with self.subTest(strategy=class_name):
                tree, _ = self.strategy_class(filename, class_name)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute):
                        self.assertNotEqual(node.attr, "iloc", "iloc access needs manual bias review")
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                        continue
                    if node.func.attr != "shift" or not node.args:
                        continue
                    offset = node.args[0]
                    is_negative = (
                        isinstance(offset, ast.UnaryOp)
                        and isinstance(offset.op, ast.USub)
                        and isinstance(offset.operand, ast.Constant)
                    )
                    self.assertFalse(is_negative, "negative shift reads future candles")

    def test_exit_causes_have_distinct_tags(self) -> None:
        expected_tags = {"rsi_overbought ", "ema_bearish_cross "}
        for filename, class_name in STRATEGIES.items():
            with self.subTest(strategy=class_name):
                tree, _ = self.strategy_class(filename, class_name)
                string_literals = {
                    node.value
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                self.assertTrue(expected_tags.issubset(string_literals))

    def test_volume_baseline_uses_only_completed_prior_candles(self) -> None:
        filename = "KoreanStarterStrategy.py"
        tree, _ = self.strategy_class(filename, STRATEGIES[filename])
        volume_mean_assignment = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "volume_mean_20"
                    for target in node.targets
                )
            ),
            None,
        )
        self.assertIsNotNone(volume_mean_assignment)
        shift_calls = [
            node
            for node in ast.walk(volume_mean_assignment.value)  # type: ignore[union-attr]
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "shift"
        ]
        self.assertEqual(len(shift_calls), 1)
        self.assertEqual(ast.literal_eval(shift_calls[0].args[0]), 1)


if __name__ == "__main__":
    unittest.main()
