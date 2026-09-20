"""Extract and display configuration summary for all repository strategies."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def get_strategy_configs(strategies_dir: Path | None = None) -> list[dict[str, object]]:
    """Parse strategy files using ast and return configuration dictionary for each strategy."""
    if strategies_dir is None:
        strategies_dir = Path(__file__).resolve().parents[1] / "strategies"

    strategy_files = [
        "VibeRsiStrategy.py",
        "KoreanStarterStrategy.py",
        "MultiTimeframeAtrStrategy.py",
    ]

    configs = []
    for filename in strategy_files:
        filepath = strategies_dir / filename
        if not filepath.exists():
            continue

        tree = ast.parse(filepath.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                vals: dict[str, object] = {}
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                        try:
                            vals[stmt.targets[0].id] = ast.literal_eval(stmt.value)
                        except Exception:
                            pass
                    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                        try:
                            vals[stmt.target.id] = ast.literal_eval(stmt.value)
                        except Exception:
                            pass

                configs.append({
                    "file": filename,
                    "class": node.name,
                    "timeframe": vals.get("timeframe", "-"),
                    "startup_candle_count": vals.get("startup_candle_count", "-"),
                    "stoploss": vals.get("stoploss", "-"),
                    "trailing_stop": vals.get("trailing_stop", False),
                    "can_short": vals.get("can_short", False),
                })

    return configs


def format_config_table(configs: list[dict[str, object]]) -> str:
    """Format strategy configuration list into a readable table."""
    lines = [
        f"{'Strategy Class':<28} | {'Timeframe':<10} | {'Startup':<10} | {'Stoploss':<10} | {'Trailing Stop'}",
        "-" * 78,
    ]
    for c in configs:
        cls_name = str(c["class"])
        tf = str(c["timeframe"])
        startup = str(c["startup_candle_count"])
        sl = f"{float(c['stoploss']) * 100:.1f}%" if isinstance(c["stoploss"], (int, float)) else str(c["stoploss"])
        ts = "YES" if c["trailing_stop"] else "NO"
        lines.append(f"{cls_name:<28} | {tf:<10} | {startup:<10} | {sl:<10} | {ts}")
    return "\n".join(lines)


def export_strategy_configs_json(configs: list[dict[str, object]], indent: int = 2) -> str:
    """Serialize strategy configuration list into formatted JSON string."""
    return json.dumps(configs, indent=indent, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Summarize strategy configurations.")
    parser.add_argument("--dir", type=str, default=None, help="Custom strategies directory path")
    parser.add_argument("--json", action="store_true", help="Output configurations as JSON")
    args = parser.parse_args()

    strategies_dir = Path(args.dir) if args.dir else None
    configs = get_strategy_configs(strategies_dir)
    if args.json:
        print(export_strategy_configs_json(configs))
    else:
        print(format_config_table(configs))


if __name__ == "__main__":
    main()
