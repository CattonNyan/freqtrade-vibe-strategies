"""Dependency-free structural checks for the strategy source files."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
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
    def script_source(self, filename: str) -> str:
        return (ROOT / "scripts" / filename).read_text(encoding="utf-8-sig")

    def script_validate_set(self, filename: str, parameter: str) -> set[str]:
        source = self.script_source(filename)
        match = re.search(
            rf'\[ValidateSet\((?P<values>[^)]*)\)\]\s*\[string(?:\[\])?\]\${parameter}\b',
            source,
        )
        self.assertIsNotNone(match, f"{parameter} ValidateSet is missing in {filename}")
        return set(re.findall(r'"([^"]+)"', match.group("values")))  # type: ignore[union-attr]

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

    def test_order_types_and_time_in_force_declared_by_every_strategy(self) -> None:
        for filename, class_name in STRATEGIES.items():
            with self.subTest(strategy=class_name):
                _, strategy = self.strategy_class(filename, class_name)
                assignments = class_assignments(strategy)

                order_types = assignments.get("order_types")
                self.assertIsInstance(order_types, dict)
                self.assertTrue({"entry", "exit", "stoploss"}.issubset(order_types.keys()))

                tif = assignments.get("order_time_in_force")
                self.assertIsInstance(tif, dict)
                self.assertEqual(tif.get("entry"), "gtc")
                self.assertEqual(tif.get("exit"), "gtc")

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

    def test_mtf_strategy_does_not_compute_unused_atr(self) -> None:
        source = (ROOT / "strategies" / "MultiTimeframeAtrStrategy.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("ta.ATR(", source)
        self.assertIn("does not depend on ATR", source)

    def test_operating_protections_are_declared_by_every_strategy(self) -> None:
        expected_methods = {"CooldownPeriod", "StoplossGuard", "MaxDrawdown"}
        for filename, class_name in STRATEGIES.items():
            with self.subTest(strategy=class_name):
                _, strategy = self.strategy_class(filename, class_name)
                protections = next(
                    (
                        node
                        for node in strategy.body
                        if isinstance(node, ast.FunctionDef) and node.name == "protections"
                    ),
                    None,
                )
                self.assertIsNotNone(protections)
                string_literals = {
                    node.value
                    for node in ast.walk(protections)  # type: ignore[arg-type]
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                self.assertTrue(expected_methods.issubset(string_literals))

    def test_protection_settings_are_consistent_and_valid(self) -> None:
        baseline: list[dict[str, object]] | None = None
        for filename, class_name in STRATEGIES.items():
            with self.subTest(strategy=class_name):
                _, strategy = self.strategy_class(filename, class_name)
                protections_method = next(
                    node
                    for node in strategy.body
                    if isinstance(node, ast.FunctionDef) and node.name == "protections"
                )
                return_node = next(
                    node for node in protections_method.body if isinstance(node, ast.Return)
                )
                protections = ast.literal_eval(return_node.value)
                by_method = {item["method"]: item for item in protections}

                self.assertEqual(
                    set(by_method),
                    {"CooldownPeriod", "StoplossGuard", "MaxDrawdown"},
                )
                for protection in protections:
                    for key in ("lookback_period", "trade_limit", "stop_duration"):
                        if key in protection:
                            self.assertIsInstance(protection[key], int)
                            self.assertGreater(protection[key], 0)

                max_drawdown = by_method["MaxDrawdown"]
                self.assertGreater(max_drawdown["max_allowed_drawdown"], 0)
                self.assertLessEqual(max_drawdown["max_allowed_drawdown"], 1)
                self.assertEqual(max_drawdown["calculation_mode"], "equity")

                if baseline is None:
                    baseline = protections
                else:
                    self.assertEqual(protections, baseline)

    def test_dry_run_example_cannot_place_live_orders(self) -> None:
        config_path = ROOT / "config" / "dry-run.example.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIs(config.get("dry_run"), True)
        self.assertEqual(config["exchange"].get("key"), "")
        self.assertEqual(config["exchange"].get("secret"), "")
        self.assertIs(config["telegram"].get("enabled"), False)

        script_source = self.script_source("Invoke-DryRun.ps1")
        self.assertIn("$dryRunConfig.telegram.enabled -ne $false", script_source)

    def test_backtest_example_remains_safe_for_local_validation(self) -> None:
        config_path = ROOT / "config" / "backtest.example.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIs(config.get("dry_run"), True)
        self.assertEqual(config.get("trading_mode"), "spot")
        self.assertIs(config.get("force_entry_enable"), False)
        self.assertEqual(config["exchange"].get("key"), "")
        self.assertEqual(config["exchange"].get("secret"), "")
        self.assertIs(config["telegram"].get("enabled"), False)

    def test_backtest_script_supports_every_strategy(self) -> None:
        source = self.script_source("Invoke-Backtest.ps1")
        self.assertEqual(
            self.script_validate_set("Invoke-Backtest.ps1", "Strategy"),
            set(STRATEGIES.values()),
        )
        self.assertIn(r"strategies\$Strategy.py", source)
        self.assertIn("Test-Path -LiteralPath $strategyPath -PathType Leaf", source)

    def test_analysis_script_supports_every_strategy(self) -> None:
        source = self.script_source("Invoke-StrategyAnalysis.ps1")
        supported = self.script_validate_set("Invoke-StrategyAnalysis.ps1", "Strategies")
        default_match = re.search(
            r'\[string\[\]\]\$Strategies\s*=\s*@\((?P<values>.*?)\)\s*,',
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(default_match, "Strategies default list is missing")
        defaults = set(
            re.findall(r'"([^"]+)"', default_match.group("values"))  # type: ignore[union-attr]
        )
        self.assertEqual(supported, set(STRATEGIES.values()))
        self.assertEqual(defaults, supported)
        self.assertIn(r"strategies\$strategy.py", source)
        self.assertIn("Test-Path -LiteralPath $strategyPath -PathType Leaf", source)

    def test_market_data_script_downloads_every_strategy_timeframe(self) -> None:
        required_timeframes: set[str] = set()
        for filename, class_name in STRATEGIES.items():
            _, strategy = self.strategy_class(filename, class_name)
            assignments = class_assignments(strategy)
            required_timeframes.add(assignments["timeframe"])  # type: ignore[arg-type]
            if "informative_timeframe" in assignments:
                required_timeframes.add(assignments["informative_timeframe"])  # type: ignore[arg-type]

        source = self.script_source("Get-MarketData.ps1")
        match = re.search(
            r'"--timeframes"\s*,(?P<values>.*?)\s*,\s*"--pairs"',
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "download-data timeframes are missing")
        downloaded_timeframes = set(
            re.findall(r'"([^"]+)"', match.group("values"))  # type: ignore[union-attr]
        )
        self.assertTrue(required_timeframes.issubset(downloaded_timeframes))

    def test_market_pair_parameters_reject_malformed_values(self) -> None:
        pair_pattern = (
            r'\[ValidateNotNullOrEmpty\(\)\]\s*'
            r'\[ValidatePattern\("\^\[A-Za-z0-9\._-\]\+/'
        )
        for filename, parameter in (
            ("Get-MarketData.ps1", "Pairs"),
            ("Invoke-Backtest.ps1", "Pairs"),
            ("Invoke-StrategyAnalysis.ps1", "Pair"),
        ):
            with self.subTest(script=filename):
                source = self.script_source(filename)
                match = re.search(
                    pair_pattern + rf'.*?\[string(?:\[\])?\]\${parameter}\b',
                    source,
                    re.DOTALL,
                )
                self.assertIsNotNone(match, f"{parameter} pair validation is missing")

    def test_backtest_accepts_and_names_requested_pairs(self) -> None:
        source = self.script_source("Invoke-Backtest.ps1")
        self.assertIn("$Pairs | Sort-Object -Unique", source)
        self.assertIn("$pairSlug", source)
        self.assertIn('"--pairs"', source)

    def test_timerange_scripts_apply_semantic_date_validation(self) -> None:
        runtime_source = self.script_source("FreqtradeRuntime.ps1")
        self.assertIn("function Assert-ValidTimerange", runtime_source)
        self.assertEqual(runtime_source.count("[datetime]::ParseExact("), 2)
        self.assertIn("if ($startDate -ge $endDate)", runtime_source)

        for filename in ("Invoke-Backtest.ps1", "Invoke-StrategyAnalysis.ps1"):
            with self.subTest(script=filename):
                source = self.script_source(filename)
                self.assertIn("Assert-ValidTimerange -Timerange $Timerange", source)

    def test_analysis_trade_amount_bounds_are_consistent(self) -> None:
        source = self.script_source("Invoke-StrategyAnalysis.ps1")
        self.assertIn(
            "if ($MinimumTradeAmount -gt $TargetedTradeAmount)",
            source,
        )

    def test_analysis_normalizes_startup_candle_candidates(self) -> None:
        source = self.script_source("Invoke-StrategyAnalysis.ps1")
        self.assertIn("$StartupCandles | Sort-Object -Unique", source)
        self.assertIn(") + $normalizedStartupCandles", source)

    def test_lookahead_results_include_the_pair_name(self) -> None:
        source = self.script_source("Invoke-StrategyAnalysis.ps1")
        self.assertIn("$pairSlug = $Pair -replace '[/:]', '-'", source)
        self.assertIn(
            '"lookahead-$strategy-$pairSlug-$Timerange.csv"',
            source,
        )

    def test_analysis_persists_command_logs(self) -> None:
        runtime_source = self.script_source("FreqtradeRuntime.ps1")
        self.assertIn("[string]$LogPath", runtime_source)
        self.assertIn("Tee-Object -FilePath $LogPath", runtime_source)
        source = self.script_source("Invoke-StrategyAnalysis.ps1")
        self.assertIn('"recursive-$strategy-$pairSlug-$Timerange.log"', source)
        self.assertIn('"lookahead-$strategy-$pairSlug-$Timerange.log"', source)
        self.assertEqual(source.count("-LogPath $"), 2)

    def test_scripts_restore_the_callers_working_directory(self) -> None:
        runtime_source = self.script_source("FreqtradeRuntime.ps1")
        self.assertIn("Push-Location -LiteralPath $repositoryRoot", runtime_source)
        self.assertIn("finally {\n        Pop-Location", runtime_source)
        for path in (ROOT / "scripts").glob("*.ps1"):
            if path.name == "FreqtradeRuntime.ps1":
                continue
            with self.subTest(script=path.name):
                self.assertNotIn("Set-Location", path.read_text(encoding="utf-8-sig"))

    def test_runtime_checks_the_docker_engine_before_use(self) -> None:
        source = self.script_source("FreqtradeRuntime.ps1")
        self.assertIn('docker info --format "{{.ServerVersion}}"', source)
        self.assertIn("$dockerEngineReady = $LASTEXITCODE -eq 0", source)
        self.assertIn("docker compose version", source)
        self.assertIn("if ($dockerReady)", source)

    def test_runtime_supports_cross_platform_virtual_environments(self) -> None:
        source = self.script_source("FreqtradeRuntime.ps1")
        self.assertIn('".venv/Scripts/freqtrade.exe"', source)
        self.assertIn('".venv/bin/freqtrade"', source)
        self.assertIn("Select-Object -First 1", source)

    def test_entry_scripts_enable_strict_mode(self) -> None:
        for path in (ROOT / "scripts").glob("*.ps1"):
            if path.name == "FreqtradeRuntime.ps1":
                continue
            with self.subTest(script=path.name):
                source = path.read_text(encoding="utf-8-sig")
                self.assertIn("Set-StrictMode -Version Latest", source)

    def test_scripts_initialize_their_output_directories(self) -> None:
        expected_directories = {
            "Get-MarketData.ps1": "user_data/data",
            "Invoke-Backtest.ps1": "user_data/backtest_results",
            "Invoke-DryRun.ps1": "user_data/db",
            "Invoke-StrategyAnalysis.ps1": "user_data/backtest_results",
        }
        runtime_source = self.script_source("FreqtradeRuntime.ps1")
        self.assertIn("function Initialize-FreqtradeDirectory", runtime_source)
        for filename, relative_path in expected_directories.items():
            with self.subTest(script=filename):
                source = self.script_source(filename)
                self.assertIn(
                    f'Initialize-FreqtradeDirectory -RelativePath "{relative_path}"',
                    source,
                )

    def test_result_scripts_require_force_before_overwriting(self) -> None:
        runtime_source = self.script_source("FreqtradeRuntime.ps1")
        self.assertIn("function Initialize-FreqtradeOutputFile", runtime_source)
        self.assertIn("if (-not $Force)", runtime_source)
        self.assertIn("Remove-Item -LiteralPath $Path -Force", runtime_source)
        for filename in ("Invoke-Backtest.ps1", "Invoke-StrategyAnalysis.ps1"):
            with self.subTest(script=filename):
                source = self.script_source(filename)
                self.assertIn("[switch]$Force", source)
                self.assertIn("Initialize-FreqtradeOutputFile", source)

    def test_backtest_and_analysis_preflight_market_data(self) -> None:
        runtime_source = self.script_source("FreqtradeRuntime.ps1")
        self.assertIn("function Assert-MarketDataAvailable", runtime_source)
        self.assertIn("Get-MarketData.ps1을 먼저 실행하세요", runtime_source)
        for filename in ("Invoke-Backtest.ps1", "Invoke-StrategyAnalysis.ps1"):
            with self.subTest(script=filename):
                source = self.script_source(filename)
                self.assertIn("Assert-MarketDataAvailable", source)
                self.assertIn('"MultiTimeframeAtrStrategy"', source)
                self.assertIn('"1h"', source)


if __name__ == "__main__":
    unittest.main()
