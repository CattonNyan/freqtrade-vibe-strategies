"""Dependency-free Quantitative Risk & Drawdown Analyzer for Freqtrade Backtest Results.

Computes institutional performance and downside risk metrics:
- Peter Martin's Ulcer Index (UI) and Martin Ratio (UPI)
- Thomas Becker's Pain Index and Pain Ratio
- Trade Expectancy and Profit Factor
- Trade Duration Asymmetry (Win vs Loss holding times)
- Calmar Ratio and Peak-to-Trough Drawdown Depth
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def calculate_ulcer_and_drawdown_metrics(trade_profits: list[float]) -> dict[str, float]:
    """Calculate cumulative equity curve, max drawdown, Ulcer Index, and Pain Index from trade profit percentages.

    trade_profits: list of profit fractions (e.g. 0.03 for +3%, -0.015 for -1.5%).
    """
    if not trade_profits:
        return {
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "ulcer_index": 0.0,
            "pain_index": 0.0,
            "martin_ratio": 0.0,
            "pain_ratio": 0.0,
            "calmar_ratio": 0.0,
        }

    # Reconstruct equity curve (starting at 1.0)
    equity = [1.0]
    for p in trade_profits:
        equity.append(equity[-1] * (1.0 + p))

    # Calculate drawdowns
    peak = equity[0]
    drawdowns_pct = []
    for val in equity[1:]:
        if val > peak:
            peak = val
        dd = (val - peak) / (peak if peak > 0 else 1.0) * 100.0
        drawdowns_pct.append(dd)

    total_return_pct = (equity[-1] - 1.0) * 100.0
    mdd_pct = abs(min(drawdowns_pct)) if drawdowns_pct else 0.0

    # Ulcer Index = sqrt( mean( DD^2 ) )
    sq_dd = [dd ** 2 for dd in drawdowns_pct]
    ulcer_index = math.sqrt(sum(sq_dd) / len(sq_dd)) if sq_dd else 0.0

    # Pain Index = mean( |DD| )
    pain_index = sum(abs(dd) for dd in drawdowns_pct) / len(drawdowns_pct) if drawdowns_pct else 0.0

    # Martin Ratio = Total Return / Ulcer Index
    martin_ratio = (total_return_pct / ulcer_index) if ulcer_index > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

    # Pain Ratio = Total Return / Pain Index
    pain_ratio = (total_return_pct / pain_index) if pain_index > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

    # Calmar Ratio = Total Return / Max Drawdown
    calmar_ratio = (total_return_pct / mdd_pct) if mdd_pct > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

    return {
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(mdd_pct, 2),
        "ulcer_index": round(ulcer_index, 3),
        "pain_index": round(pain_index, 3),
        "martin_ratio": round(martin_ratio, 3),
        "pain_ratio": round(pain_ratio, 3),
        "calmar_ratio": round(calmar_ratio, 3),
    }


def calculate_trade_expectancy(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate trade-level win/loss statistics, profit factor, and expectancy."""
    if not trades:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "expectancy_pct": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "win_loss_ratio": 0.0,
            "avg_duration_min": 0.0,
        }

    wins = []
    losses = []
    draws = 0
    durations = []

    for t in trades:
        # Freqtrade trade profit percentage is typically in 'profit_ratio' (0.05 = 5%)
        profit = float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
        duration_min = float(t.get("trade_duration", t.get("duration", 0.0)))
        durations.append(duration_min)

        if profit > 1e-6:
            wins.append(profit * 100.0)
        elif profit < -1e-6:
            losses.append(abs(profit * 100.0))
        else:
            draws += 1

    total_trades = len(trades)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

    sum_wins = sum(wins)
    sum_losses = sum(losses)
    profit_factor = (sum_wins / sum_losses) if sum_losses > 0 else (999.0 if sum_wins > 0 else 0.0)

    avg_win = (sum_wins / win_count) if win_count > 0 else 0.0
    avg_loss = (sum_losses / loss_count) if loss_count > 0 else 0.0
    win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)

    # Expectancy = (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
    p_win = win_count / total_trades if total_trades > 0 else 0.0
    p_loss = loss_count / total_trades if total_trades > 0 else 0.0
    expectancy = (p_win * avg_win) - (p_loss * avg_loss)

    avg_duration = sum(durations) / len(durations) if durations else 0.0

    return {
        "total_trades": total_trades,
        "wins": win_count,
        "losses": loss_count,
        "draws": draws,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_pct": round(expectancy, 3),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "win_loss_ratio": round(win_loss_ratio, 2),
        "avg_duration_min": round(avg_duration, 1),
    }


def parse_freqtrade_backtest_json(json_data: dict[str, Any]) -> dict[str, Any]:
    """Parse strategy results dictionary from Freqtrade backtest JSON."""
    strategy_results = {}
    strategy_dict = json_data.get("strategy", {})

    for strat_name, strat_data in strategy_dict.items():
        trades = strat_data.get("trades", [])
        profit_ratios = [
            float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
            for t in trades
        ]

        dd_metrics = calculate_ulcer_and_drawdown_metrics(profit_ratios)
        trade_metrics = calculate_trade_expectancy(trades)

        combined = {
            "strategy": strat_name,
            **trade_metrics,
            **dd_metrics,
        }
        strategy_results[strat_name] = combined

    return strategy_results


def generate_markdown_report(analysis_results: dict[str, Any]) -> str:
    """Generate Markdown report for backtest quantitative analysis."""
    lines = [
        "# 📊 Freqtrade 전략 심층 퀀트 리스크 및 하방 위험 분석 보고서",
        "",
        "| 전략명 | 총 거래 | 승률 | 손익비(P.F.) | 기대값(Trade Exp.) | 최대낙폭(MDD) | 궤양지수(Ulcer Index) | 마틴 비율(UPI) | 칼마 비율 |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for name, data in analysis_results.items():
        lines.append(
            f"| **{name}** | {data['total_trades']}회 | {data['win_rate_pct']:.1f}% | "
            f"{data['profit_factor']:.2f} | {data['expectancy_pct']:+.3f}% | "
            f"-{data['max_drawdown_pct']:.2f}% | {data['ulcer_index']:.2f}% | "
            f"{data['martin_ratio']:.2f} | {data['calmar_ratio']:.2f} |"
        )

    lines.append("")
    lines.append("### 💡 지표 설명 (Methodology)")
    lines.append("- **궤양지수 (Ulcer Index, Peter Martin 1987)**: 고점 대비 하락폭(Drawdown)의 제곱평균제곱근(RMS). 단순 변동성과 달리 상승 변동성은 처벌하지 않고 깊고 긴 하락장만을 집중 가중 처벌합니다.")
    lines.append("- **마틴 비율 (Martin Ratio / UPI)**: 총 수익률을 궤양지수로 나눈 값으로, 샤프 지수보다 추세추종 전략의 실질 하방 위험 대비 성과를 정확하게 평가합니다.")
    lines.append("- **거래 기대값 (Trade Expectancy)**: (승률 × 평균 수익률) - (패율 × 평균 손실률). 1회 거래당 기대되는 통계적 엣지(Edge)입니다.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze Freqtrade backtest results for Ulcer Index and Expectancy")
    parser.add_argument("file", type=str, help="Path to backtest-result.json file")
    parser.add_argument("--output", "-o", type=str, default=None, help="Optional output Markdown path")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        raise FileNotFoundError(f"Backtest result file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = parse_freqtrade_backtest_json(data)
    md_content = generate_markdown_report(results)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"[+] Quant analysis report exported to: {out_path}")
    else:
        print(md_content)


if __name__ == "__main__":
    main()
