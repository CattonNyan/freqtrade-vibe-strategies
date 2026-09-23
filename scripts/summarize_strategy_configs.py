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

    if strategies_dir.exists():
        strategy_files = sorted([
            p.name for p in strategies_dir.glob("*.py")
            if p.name != "__init__.py" and not p.name.startswith(".")
        ])
    else:
        strategy_files = []

    if not strategy_files:
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
                    "use_custom_stoploss": vals.get("use_custom_stoploss", False),
                    "process_only_new_candles": vals.get("process_only_new_candles", True),
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


def format_config_markdown(configs: list[dict[str, object]]) -> str:
    """Format strategy configuration list into a GitHub Flavored Markdown table."""
    lines = [
        "| Strategy Class | Timeframe | Startup Candles | Stoploss | Trailing Stop | Custom Stoploss | Process New Only |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for c in configs:
        cls_name = str(c["class"])
        tf = str(c["timeframe"])
        startup = str(c["startup_candle_count"])
        sl = f"{float(c['stoploss']) * 100:.1f}%" if isinstance(c["stoploss"], (int, float)) else str(c["stoploss"])
        ts = "YES" if c["trailing_stop"] else "NO"
        csl = "YES" if c.get("use_custom_stoploss") else "NO"
        pno = "YES" if c.get("process_only_new_candles", True) else "NO"
        lines.append(f"| **{cls_name}** | {tf} | {startup} | {sl} | {ts} | {csl} | {pno} |")
    return "\n".join(lines)


def sort_strategy_configs(
    configs: list[dict[str, object]],
    sort_by: str = "class",
    reverse: bool = False,
) -> list[dict[str, object]]:
    """Sort strategy configuration list by specified field."""
    def _timeframe_to_minutes(tf: object) -> int:
        s = str(tf).strip().lower()
        if s.endswith("m"):
            try:
                return int(s[:-1])
            except ValueError:
                pass
        elif s.endswith("h"):
            try:
                return int(s[:-1]) * 60
            except ValueError:
                pass
        elif s.endswith("d"):
            try:
                return int(s[:-1]) * 1440
            except ValueError:
                pass
        return 999999

    def _sort_key(c: dict[str, object]):
        if sort_by == "timeframe":
            return _timeframe_to_minutes(c.get("timeframe", ""))
        elif sort_by == "startup":
            val = c.get("startup_candle_count", 0)
            return int(val) if isinstance(val, (int, float)) else 0
        elif sort_by == "stoploss":
            val = c.get("stoploss", 0.0)
            return float(val) if isinstance(val, (int, float)) else 0.0
        return str(c.get("class", "")).lower()

    return sorted(configs, key=_sort_key, reverse=reverse)


def filter_strategy_configs(
    configs: list[dict[str, object]],
    has_trailing: bool | None = None,
    custom_stoploss_only: bool = False,
    timeframe: str | None = None,
) -> list[dict[str, object]]:
    """Filter strategy configuration list based on criteria."""
    filtered = list(configs)
    if has_trailing is not None:
        filtered = [c for c in filtered if bool(c.get("trailing_stop")) == has_trailing]
    if custom_stoploss_only:
        filtered = [c for c in filtered if bool(c.get("use_custom_stoploss"))]
    if timeframe:
        filtered = [c for c in filtered if str(c.get("timeframe", "")).strip().lower() == timeframe.strip().lower()]
    return filtered


def export_strategy_configs_json(configs: list[dict[str, object]], indent: int = 2) -> str:
    """Serialize strategy configuration list into formatted JSON string."""
    return json.dumps(configs, indent=indent, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Summarize strategy configurations.")
    parser.add_argument("--dir", type=str, default=None, help="Custom strategies directory path")
    parser.add_argument("--json", action="store_true", help="Output configurations as JSON")
    parser.add_argument("--markdown", "-m", action="store_true", help="Output configurations as Markdown table")
    parser.add_argument(
        "--sort-by",
        choices=["class", "timeframe", "startup", "stoploss"],
        default="class",
        help="Field to sort strategies by (class, timeframe, startup, stoploss)",
    )
    parser.add_argument("--reverse", action="store_true", help="Sort in descending order")
    parser.add_argument("--has-trailing", action="store_true", help="Show only strategies with trailing stop enabled")
    parser.add_argument(
        "--custom-stoploss-only", action="store_true", help="Show only strategies that define custom stoploss"
    )
    parser.add_argument(
        "--filter-timeframe",
        type=str,
        default=None,
        help="Filter strategies matching a specific timeframe (e.g. 5m, 15m, 1h)",
    )
    parser.add_argument("--output", "-o", type=str, default=None, help="Path to write output report to")
    args = parser.parse_args()

    strategies_dir = Path(args.dir) if args.dir else None
    configs = get_strategy_configs(strategies_dir)

    if args.has_trailing:
        configs = filter_strategy_configs(configs, has_trailing=True)
    if args.custom_stoploss_only:
        configs = filter_strategy_configs(configs, custom_stoploss_only=True)
    if args.filter_timeframe:
        configs = filter_strategy_configs(configs, timeframe=args.filter_timeframe)

    configs = sort_strategy_configs(configs, sort_by=args.sort_by, reverse=args.reverse)

    if args.json:
        output_text = export_strategy_configs_json(configs)
    elif args.markdown:
        output_text = format_config_markdown(configs)
    else:
        output_text = format_config_table(configs)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"[+] Strategy configuration summary written to: {out_path}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
