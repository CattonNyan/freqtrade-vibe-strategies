"""Extract and display configuration summary for all repository strategies."""

from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import sys
from pathlib import Path


def get_initial_roi(roi: object) -> float | None:
    """Extract initial target profit ratio from minimal_roi dictionary."""
    if not isinstance(roi, dict) or not roi:
        return None
    if "0" in roi and isinstance(roi["0"], (int, float)):
        return float(roi["0"])
    if 0 in roi and isinstance(roi[0], (int, float)):
        return float(roi[0])
    try:
        int_keys = sorted(
            [(int(k), v) for k, v in roi.items() if isinstance(v, (int, float))],
            key=lambda x: x[0],
        )
        if int_keys:
            return float(int_keys[0][1])
    except (ValueError, TypeError):
        pass
    return None


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
                    "informative_timeframe": vals.get("informative_timeframe", "-"),
                    "startup_candle_count": vals.get("startup_candle_count", "-"),
                    "stoploss": vals.get("stoploss", "-"),
                    "trailing_stop": vals.get("trailing_stop", False),
                    "use_custom_stoploss": vals.get("use_custom_stoploss", False),
                    "process_only_new_candles": vals.get("process_only_new_candles", True),
                    "can_short": vals.get("can_short", False),
                    "use_exit_signal": vals.get("use_exit_signal", True),
                    "minimal_roi": vals.get("minimal_roi", {}),
                })

    return configs


def compute_config_summary_stats(configs: list[dict[str, object]]) -> dict[str, object]:
    """Compute aggregate statistics across strategy configurations."""
    total = len(configs)
    if total == 0:
        return {
            "total_strategies": 0,
            "timeframe_distribution": {},
            "trailing_stop_count": 0,
            "trailing_stop_pct": 0.0,
            "custom_stoploss_count": 0,
            "custom_stoploss_pct": 0.0,
            "can_short_count": 0,
            "can_short_pct": 0.0,
            "multi_timeframe_count": 0,
            "multi_timeframe_pct": 0.0,
            "exit_signal_count": 0,
            "exit_signal_pct": 0.0,
            "avg_stoploss_pct": 0.0,
            "min_stoploss_pct": 0.0,
            "max_stoploss_pct": 0.0,
            "avg_initial_roi_pct": 0.0,
        }

    tf_counts: dict[str, int] = {}
    trailing_count = 0
    custom_sl_count = 0
    can_short_count = 0
    mtf_count = 0
    exit_signal_count = 0
    stoplosses: list[float] = []
    initial_rois: list[float] = []

    for c in configs:
        tf = str(c.get("timeframe", "-"))
        tf_counts[tf] = tf_counts.get(tf, 0) + 1
        if c.get("trailing_stop"):
            trailing_count += 1
        if c.get("use_custom_stoploss"):
            custom_sl_count += 1
        if c.get("can_short"):
            can_short_count += 1
        info_tf = c.get("informative_timeframe")
        if info_tf and str(info_tf).strip() not in ("-", "", "None"):
            mtf_count += 1
        if c.get("use_exit_signal", True):
            exit_signal_count += 1
        sl = c.get("stoploss")
        if isinstance(sl, (int, float)):
            stoplosses.append(float(sl) * 100.0)
        init_roi = get_initial_roi(c.get("minimal_roi"))
        if init_roi is not None:
            initial_rois.append(init_roi * 100.0)

    avg_sl = (sum(stoplosses) / len(stoplosses)) if stoplosses else 0.0
    min_sl = min(stoplosses) if stoplosses else 0.0
    max_sl = max(stoplosses) if stoplosses else 0.0
    avg_roi = (sum(initial_rois) / len(initial_rois)) if initial_rois else 0.0

    return {
        "total_strategies": total,
        "timeframe_distribution": tf_counts,
        "trailing_stop_count": trailing_count,
        "trailing_stop_pct": round((trailing_count / total) * 100.0, 1),
        "custom_stoploss_count": custom_sl_count,
        "custom_stoploss_pct": round((custom_sl_count / total) * 100.0, 1),
        "can_short_count": can_short_count,
        "can_short_pct": round((can_short_count / total) * 100.0, 1),
        "multi_timeframe_count": mtf_count,
        "multi_timeframe_pct": round((mtf_count / total) * 100.0, 1),
        "exit_signal_count": exit_signal_count,
        "exit_signal_pct": round((exit_signal_count / total) * 100.0, 1),
        "avg_stoploss_pct": round(avg_sl, 2),
        "min_stoploss_pct": round(min_sl, 2),
        "max_stoploss_pct": round(max_sl, 2),
        "avg_initial_roi_pct": round(avg_roi, 2),
    }


def format_config_summary_stats(stats: dict[str, object]) -> str:
    """Format repository summary statistics into a terminal-friendly block."""
    tf_str = ", ".join(f"{k}: {v}" for k, v in stats.get("timeframe_distribution", {}).items()) or "None"
    lines = [
        "================ Strategy Repository Statistics ================",
        f"  Total Strategies        : {stats['total_strategies']}",
        f"  Timeframe Breakdown     : {tf_str}",
        f"  Multi-Timeframe Active  : {stats.get('multi_timeframe_count', 0)} ({stats.get('multi_timeframe_pct', 0.0)}%)",
        f"  Trailing Stop Enabled   : {stats['trailing_stop_count']} ({stats['trailing_stop_pct']}%)",
        f"  Custom Stoploss Defined : {stats['custom_stoploss_count']} ({stats['custom_stoploss_pct']}%)",
        f"  Exit Signal Enabled     : {stats.get('exit_signal_count', 0)} ({stats.get('exit_signal_pct', 0.0)}%)",
        f"  Shorting Supported      : {stats['can_short_count']} ({stats['can_short_pct']}%)",
        f"  Fixed Stoploss Range    : {stats['avg_stoploss_pct']:+.1f}% avg (Min: {stats['min_stoploss_pct']:+.1f}%, Max: {stats['max_stoploss_pct']:+.1f}%)",
        f"  Avg Initial ROI Target  : {stats.get('avg_initial_roi_pct', 0.0):+.1f}%",
        "================================================================",
    ]
    return "\n".join(lines)


def format_config_table(configs: list[dict[str, object]]) -> str:
    """Format strategy configuration list into a readable table."""
    lines = [
        f"{'Strategy Class':<26} | {'TF':<5} | {'Info TF':<7} | {'Startup':<8} | {'Stoploss':<9} | {'Trailing':<8} | {'Custom SL':<9} | {'Initial ROI'}",
        "-" * 98,
    ]
    for c in configs:
        cls_name = str(c.get("class", ""))
        tf = str(c.get("timeframe", "-"))
        info_tf = str(c.get("informative_timeframe", "-"))
        startup = str(c.get("startup_candle_count", "-"))
        sl = f"{float(c['stoploss']) * 100:.1f}%" if isinstance(c.get("stoploss"), (int, float)) else str(c.get("stoploss", "-"))
        ts = "YES" if c.get("trailing_stop") else "NO"
        csl = "YES" if c.get("use_custom_stoploss") else "NO"
        init_roi = get_initial_roi(c.get("minimal_roi"))
        roi_str = f"+{init_roi * 100:.1f}%" if init_roi is not None else "-"
        lines.append(f"{cls_name:<26} | {tf:<5} | {info_tf:<7} | {startup:<8} | {sl:<9} | {ts:<8} | {csl:<9} | {roi_str}")
    return "\n".join(lines)


def format_config_markdown(configs: list[dict[str, object]], include_stats: bool = False) -> str:
    """Format strategy configuration list into a GitHub Flavored Markdown table."""
    lines = []
    if include_stats:
        stats = compute_config_summary_stats(configs)
        tf_str = ", ".join(f"`{k}`: {v}" for k, v in stats.get("timeframe_distribution", {}).items()) or "None"
        lines.extend([
            "### 📊 Strategy Repository Summary",
            f"- **Total Strategies**: {stats['total_strategies']}",
            f"- **Timeframe Distribution**: {tf_str}",
            f"- **Multi-Timeframe Adoption**: {stats.get('multi_timeframe_count', 0)} ({stats.get('multi_timeframe_pct', 0.0)}%)",
            f"- **Trailing Stop Adoption**: {stats['trailing_stop_count']} ({stats['trailing_stop_pct']}%)",
            f"- **Custom Stoploss Adoption**: {stats['custom_stoploss_count']} ({stats['custom_stoploss_pct']}%)",
            f"- **Exit Signal Adoption**: {stats.get('exit_signal_count', 0)} ({stats.get('exit_signal_pct', 0.0)}%)",
            f"- **Shorting Supported**: {stats['can_short_count']} ({stats['can_short_pct']}%)",
            f"- **Fixed Stoploss**: {stats['avg_stoploss_pct']:+.1f}% avg (Min: {stats['min_stoploss_pct']:+.1f}%, Max: {stats['max_stoploss_pct']:+.1f}%)",
            f"- **Avg Initial ROI**: {stats.get('avg_initial_roi_pct', 0.0):+.1f}%",
            "",
        ])
    lines.extend([
        "| Strategy Class | Timeframe | Informative TF | Startup Candles | Stoploss | Trailing Stop | Custom Stoploss | Exit Signal | Can Short | Process New Only | Initial ROI |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])
    for c in configs:
        cls_name = str(c.get("class", ""))
        tf = str(c.get("timeframe", "-"))
        info_tf = str(c.get("informative_timeframe", "-"))
        startup = str(c.get("startup_candle_count", "-"))
        sl = f"{float(c['stoploss']) * 100:.1f}%" if isinstance(c.get("stoploss"), (int, float)) else str(c.get("stoploss", "-"))
        ts = "YES" if c.get("trailing_stop") else "NO"
        csl = "YES" if c.get("use_custom_stoploss") else "NO"
        es = "YES" if c.get("use_exit_signal", True) else "NO"
        cs = "YES" if c.get("can_short") else "NO"
        pno = "YES" if c.get("process_only_new_candles", True) else "NO"
        init_roi = get_initial_roi(c.get("minimal_roi"))
        roi_str = f"+{init_roi * 100:.1f}%" if init_roi is not None else "-"
        lines.append(f"| **{cls_name}** | {tf} | {info_tf} | {startup} | {sl} | {ts} | {csl} | {es} | {cs} | {pno} | {roi_str} |")
    return "\n".join(lines)


def format_config_csv(configs: list[dict[str, object]]) -> str:
    """Format strategy configuration list into a CSV string."""
    headers = [
        "file",
        "class",
        "timeframe",
        "informative_timeframe",
        "startup_candle_count",
        "stoploss",
        "trailing_stop",
        "use_custom_stoploss",
        "use_exit_signal",
        "can_short",
        "process_only_new_candles",
        "initial_roi_pct",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for c in configs:
        row = dict(c)
        row["informative_timeframe"] = c.get("informative_timeframe", "-")
        row["use_exit_signal"] = c.get("use_exit_signal", True)
        init_roi = get_initial_roi(c.get("minimal_roi"))
        row["initial_roi_pct"] = round(init_roi * 100.0, 2) if init_roi is not None else ""
        writer.writerow(row)
    return output.getvalue()


def export_config_csv(configs: list[dict[str, object]], output_path: str | Path) -> Path:
    """Export strategy configurations directly to a CSV file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = format_config_csv(configs)
    path.write_text(content, encoding="utf-8")
    return path



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
        elif sort_by == "informative_timeframe":
            return _timeframe_to_minutes(c.get("informative_timeframe", ""))
        elif sort_by == "startup":
            val = c.get("startup_candle_count", 0)
            return int(val) if isinstance(val, (int, float)) else 0
        elif sort_by == "stoploss":
            val = c.get("stoploss", 0.0)
            return float(val) if isinstance(val, (int, float)) else 0.0
        elif sort_by == "roi":
            init_roi = get_initial_roi(c.get("minimal_roi"))
            return float(init_roi) if init_roi is not None else -999.0
        return str(c.get("class", "")).lower()

    return sorted(configs, key=_sort_key, reverse=reverse)


def filter_strategy_configs(
    configs: list[dict[str, object]],
    has_trailing: bool | None = None,
    custom_stoploss_only: bool = False,
    timeframe: str | None = None,
    can_short_only: bool = False,
    multi_timeframe_only: bool = False,
    exit_signal_only: bool = False,
) -> list[dict[str, object]]:
    """Filter strategy configuration list based on criteria."""
    filtered = list(configs)
    if has_trailing is not None:
        filtered = [c for c in filtered if bool(c.get("trailing_stop")) == has_trailing]
    if custom_stoploss_only:
        filtered = [c for c in filtered if bool(c.get("use_custom_stoploss"))]
    if timeframe:
        filtered = [c for c in filtered if str(c.get("timeframe", "")).strip().lower() == timeframe.strip().lower()]
    if can_short_only:
        filtered = [c for c in filtered if bool(c.get("can_short"))]
    if multi_timeframe_only:
        filtered = [c for c in filtered if str(c.get("informative_timeframe", "-")).strip() not in ("-", "", "None")]
    if exit_signal_only:
        filtered = [c for c in filtered if bool(c.get("use_exit_signal", True))]
    return filtered


def export_strategy_configs_json(
    configs: list[dict[str, object]],
    indent: int = 2,
    include_stats: bool = False,
) -> str:
    """Serialize strategy configuration list into formatted JSON string."""
    if include_stats:
        payload: dict[str, object] = {
            "stats": compute_config_summary_stats(configs),
            "strategies": configs,
        }
    else:
        payload = configs
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def format_config_html(configs: list[dict[str, object]], include_stats: bool = True) -> str:
    """Format strategy configuration list into a standalone dark-themed HTML report."""
    stats = compute_config_summary_stats(configs)
    stats_html = ""
    if include_stats and stats["total_strategies"] > 0:
        stats_html = f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">총 전략 수</div>
                <div class="stat-value">{stats['total_strategies']}개</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">다중 타임프레임 채택률</div>
                <div class="stat-value">{stats.get('multi_timeframe_pct', 0.0)}% <span class="stat-sub">({stats.get('multi_timeframe_count', 0)}개)</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-label">트레일링 스탑 채택률</div>
                <div class="stat-value">{stats['trailing_stop_pct']}% <span class="stat-sub">({stats['trailing_stop_count']}개)</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-label">커스텀 스톱로스</div>
                <div class="stat-value">{stats['custom_stoploss_pct']}% <span class="stat-sub">({stats['custom_stoploss_count']}개)</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-label">청산 시그널 지원</div>
                <div class="stat-value">{stats.get('exit_signal_pct', 0.0)}% <span class="stat-sub">({stats.get('exit_signal_count', 0)}개)</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-label">공매도(Short) 지원</div>
                <div class="stat-value">{stats['can_short_pct']}% <span class="stat-sub">({stats['can_short_count']}개)</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-label">평균 고정 손절폭</div>
                <div class="stat-value">{stats['avg_stoploss_pct']:+.1f}% <span class="stat-sub">({stats['min_stoploss_pct']:+.1f}% ~ {stats['max_stoploss_pct']:+.1f}%)</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-label">평균 초기 목표 수익률</div>
                <div class="stat-value">{stats.get('avg_initial_roi_pct', 0.0):+.1f}%</div>
            </div>
        </div>
        """

    rows = []
    for c in configs:
        cls_name = str(c.get("class", ""))
        filename = str(c.get("file", ""))
        tf = str(c.get("timeframe", "-"))
        info_tf = str(c.get("informative_timeframe", "-"))
        startup = str(c.get("startup_candle_count", "-"))
        sl_raw = c.get("stoploss", "-")
        sl_str = f"{float(sl_raw) * 100:.1f}%" if isinstance(sl_raw, (int, float)) else str(sl_raw)
        ts = "YES" if c.get("trailing_stop") else "NO"
        csl = "YES" if c.get("use_custom_stoploss") else "NO"
        es = "YES" if c.get("use_exit_signal", True) else "NO"
        cs = "YES" if c.get("can_short") else "NO"
        pno = "YES" if c.get("process_only_new_candles", True) else "NO"

        init_roi = get_initial_roi(c.get("minimal_roi"))
        roi_str = f"+{init_roi * 100:.1f}%" if init_roi is not None else "-"
        roi_color = "#3fb950" if (init_roi is not None and init_roi > 0) else "var(--text)"

        ts_class = "badge-success" if ts == "YES" else "badge-muted"
        csl_class = "badge-success" if csl == "YES" else "badge-muted"
        es_class = "badge-success" if es == "YES" else "badge-muted"
        cs_class = "badge-warning" if cs == "YES" else "badge-muted"
        info_badge = f'<span class="badge badge-primary">{info_tf}</span>' if info_tf != "-" else '<span class="badge badge-muted">-</span>'

        rows.append(f"""
        <tr>
            <td><strong>{cls_name}</strong><br><small style="color:#8b949e">{filename}</small></td>
            <td><span class="badge badge-primary">{tf}</span></td>
            <td>{info_badge}</td>
            <td>{startup}</td>
            <td style="color:#f85149; font-weight:600;">{sl_str}</td>
            <td style="color:{roi_color}; font-weight:600;">{roi_str}</td>
            <td><span class="badge {ts_class}">{ts}</span></td>
            <td><span class="badge {csl_class}">{csl}</span></td>
            <td><span class="badge {es_class}">{es}</span></td>
            <td><span class="badge {cs_class}">{cs}</span></td>
            <td>{pno}</td>
        </tr>
        """)

    tbody = "".join(rows) if rows else '<tr><td colspan="11">전략 데이터 없음</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Freqtrade Strategy Configuration Matrix</title>
    <style>
        :root {{
            --bg: #0d1117;
            --surface: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --heading: #f0f6fc;
            --primary: #58a6ff;
            --green: #3fb950;
            --yellow: #d29922;
            --red: #f85149;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 32px 24px;
            line-height: 1.5;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{ margin-bottom: 28px; }}
        h1 {{ color: var(--heading); font-size: 26px; margin-bottom: 8px; }}
        p.subtitle {{ color: #8b949e; font-size: 14px; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 14px;
            margin-bottom: 24px;
        }}
        .stat-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
        }}
        .stat-label {{ font-size: 12px; color: #8b949e; margin-bottom: 6px; }}
        .stat-value {{ font-size: 20px; font-weight: 700; color: var(--heading); }}
        .stat-sub {{ font-size: 13px; font-weight: 400; color: #8b949e; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
            margin-top: 16px;
        }}
        th, td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            font-size: 14px;
        }}
        th {{ background: #21262d; color: var(--heading); font-weight: 600; font-size: 13px; }}
        tr:last-child td {{ border-bottom: none; }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            font-size: 12px;
            font-weight: 600;
            border-radius: 12px;
        }}
        .badge-primary {{ background: rgba(88, 166, 255, 0.15); color: var(--primary); }}
        .badge-success {{ background: rgba(63, 185, 80, 0.15); color: var(--green); }}
        .badge-warning {{ background: rgba(210, 153, 34, 0.15); color: var(--yellow); }}
        .badge-muted {{ background: rgba(139, 148, 158, 0.15); color: #8b949e; }}
        footer {{
            margin-top: 36px;
            text-align: center;
            font-size: 12px;
            color: #8b949e;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Freqtrade Strategy Configuration Matrix</h1>
            <p class="subtitle">Repository Strategy Parameters, Safety Rails & Timeframe Matrix</p>
        </header>
        {stats_html}
        <table>
            <thead>
                <tr>
                    <th>전략 클래스 (파일명)</th>
                    <th>기본 TF</th>
                    <th>보조 TF</th>
                    <th>초기 캔들</th>
                    <th>기본 손절폭</th>
                    <th>초기 ROI</th>
                    <th>트레일링 스탑</th>
                    <th>커스텀 손절</th>
                    <th>청산 시그널</th>
                    <th>공매도(Short)</th>
                    <th>신규 봉만 처리</th>
                </tr>
            </thead>
            <tbody>
                {tbody}
            </tbody>
        </table>
        <footer>
            Generated by Freqtrade Vibe Strategies | Strategy Configuration Summarizer
        </footer>
    </div>
</body>
</html>
"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Summarize strategy configurations.")
    parser.add_argument("--dir", type=str, default=None, help="Custom strategies directory path")
    parser.add_argument("--json", action="store_true", help="Output configurations as JSON")
    parser.add_argument("--csv", action="store_true", help="Output configurations as CSV")
    parser.add_argument("--markdown", "-m", action="store_true", help="Output configurations as Markdown table")
    parser.add_argument("--html", "-H", action="store_true", help="Output configurations as standalone HTML report")
    parser.add_argument("--stats", "-s", action="store_true", help="Display repository summary statistics")
    parser.add_argument(
        "--sort-by",
        choices=["class", "timeframe", "startup", "stoploss", "roi", "informative_timeframe"],
        default="class",
        help="Field to sort strategies by (class, timeframe, startup, stoploss, roi, informative_timeframe)",
    )
    parser.add_argument("--reverse", action="store_true", help="Sort in descending order")
    parser.add_argument("--has-trailing", action="store_true", help="Show only strategies with trailing stop enabled")
    parser.add_argument(
        "--custom-stoploss-only", action="store_true", help="Show only strategies that define custom stoploss"
    )
    parser.add_argument(
        "--can-short-only", action="store_true", help="Show only strategies supporting short positions"
    )
    parser.add_argument(
        "--multi-timeframe-only", action="store_true", help="Show only strategies utilizing multi-timeframe informative candles"
    )
    parser.add_argument(
        "--exit-signal-only", action="store_true", help="Show only strategies using exit signals"
    )
    parser.add_argument(
        "--filter-timeframe",
        type=str,
        default=None,
        help="Filter strategies matching a specific timeframe (e.g. 5m, 15m, 1h)",
    )
    parser.add_argument("--export-csv", type=str, default=None, help="Export strategy configurations directly to specified CSV file")
    parser.add_argument("--output", "-o", type=str, default=None, help="Path to write output report to")
    args = parser.parse_args()

    strategies_dir = Path(args.dir) if args.dir else None
    configs = get_strategy_configs(strategies_dir)

    if args.has_trailing:
        configs = filter_strategy_configs(configs, has_trailing=True)
    if args.custom_stoploss_only:
        configs = filter_strategy_configs(configs, custom_stoploss_only=True)
    if args.can_short_only:
        configs = filter_strategy_configs(configs, can_short_only=True)
    if args.multi_timeframe_only:
        configs = filter_strategy_configs(configs, multi_timeframe_only=True)
    if args.exit_signal_only:
        configs = filter_strategy_configs(configs, exit_signal_only=True)
    if args.filter_timeframe:
        configs = filter_strategy_configs(configs, timeframe=args.filter_timeframe)

    configs = sort_strategy_configs(configs, sort_by=args.sort_by, reverse=args.reverse)

    if args.json:
        output_text = export_strategy_configs_json(configs, include_stats=args.stats)
    elif args.csv:
        output_text = format_config_csv(configs)
    elif args.markdown:
        output_text = format_config_markdown(configs, include_stats=args.stats)
    elif args.html:
        output_text = format_config_html(configs, include_stats=True)
    else:
        table_text = format_config_table(configs)
        if args.stats:
            stats = compute_config_summary_stats(configs)
            output_text = f"{format_config_summary_stats(stats)}\n\n{table_text}"
        else:
            output_text = table_text

    if args.export_csv:
        csv_path = export_config_csv(configs, args.export_csv)
        print(f"[+] Strategy configuration CSV written to: {csv_path}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"[+] Strategy configuration summary written to: {out_path}")
    elif not args.export_csv:
        print(output_text)


if __name__ == "__main__":
    main()
