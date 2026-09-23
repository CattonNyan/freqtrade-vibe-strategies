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


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert value to float, replacing NaN, Inf, or invalid types with default."""
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def calculate_ulcer_and_drawdown_metrics(trade_profits: list[float]) -> dict[str, float]:
    """Calculate cumulative equity curve, max drawdown, Ulcer Index, and Pain Index from trade profit percentages.

    trade_profits: list of profit fractions (e.g. 0.03 for +3%, -0.015 for -1.5%).
    """
    clean_profits = [_safe_float(p) for p in trade_profits] if trade_profits else []
    if not clean_profits:
        return {
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "ulcer_index": 0.0,
            "pain_index": 0.0,
            "martin_ratio": 0.0,
            "pain_ratio": 0.0,
            "calmar_ratio": 0.0,
            "recovery_factor": 0.0,
            "downside_deviation_pct": 0.0,
            "sortino_ratio": 0.0,
            "burke_ratio": 0.0,
            "time_underwater_pct": 0.0,
            "avg_drawdown_pct": 0.0,
            "max_drawdown_duration_trades": 0,
        }

    # Reconstruct equity curve (starting at 1.0)
    equity = [1.0]
    for p in clean_profits:
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

    # Burke Ratio = Total Return / sqrt( sum( DD^2 ) )
    sum_sq_dd = sum(sq_dd)
    burke_ratio = (
        (total_return_pct / math.sqrt(sum_sq_dd))
        if sum_sq_dd > 1e-6
        else (999.0 if total_return_pct > 0 else 0.0)
    )

    # Time Underwater & Average Drawdown Depth
    underwater_trades = [dd for dd in drawdowns_pct if dd < -1e-6]
    time_underwater_pct = (len(underwater_trades) / len(drawdowns_pct) * 100.0) if drawdowns_pct else 0.0
    avg_drawdown_pct = (sum(abs(dd) for dd in underwater_trades) / len(underwater_trades)) if underwater_trades else 0.0

    # Pain Index = mean( |DD| )
    pain_index = sum(abs(dd) for dd in drawdowns_pct) / len(drawdowns_pct) if drawdowns_pct else 0.0

    # Martin Ratio = Total Return / Ulcer Index
    martin_ratio = (total_return_pct / ulcer_index) if ulcer_index > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

    # Pain Ratio = Total Return / Pain Index
    pain_ratio = (total_return_pct / pain_index) if pain_index > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

    # Calmar Ratio = Total Return / Max Drawdown
    calmar_ratio = (total_return_pct / mdd_pct) if mdd_pct > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

    # Recovery Factor = Total Return / Max Drawdown
    recovery_factor = (total_return_pct / mdd_pct) if mdd_pct > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

    # Downside Deviation (RMS of negative returns) and Sortino Ratio
    negative_returns = [p for p in clean_profits if p < 0.0]
    downside_dev = (
        math.sqrt(sum(p ** 2 for p in negative_returns) / len(clean_profits))
        if clean_profits and negative_returns
        else 0.0
    )
    downside_dev_pct = downside_dev * 100.0
    sortino_ratio = (
        (total_return_pct / downside_dev_pct)
        if downside_dev_pct > 1e-6
        else (999.0 if total_return_pct > 0 else 0.0)
    )

    # Calculate max underwater trade duration (streak of consecutive trades spent below peak)
    curr_underwater = 0
    max_underwater = 0
    for dd in drawdowns_pct:
        if dd < -1e-6:
            curr_underwater += 1
            if curr_underwater > max_underwater:
                max_underwater = curr_underwater
        else:
            curr_underwater = 0

    return {
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(mdd_pct, 2),
        "ulcer_index": round(ulcer_index, 3),
        "pain_index": round(pain_index, 3),
        "martin_ratio": round(martin_ratio, 3),
        "pain_ratio": round(pain_ratio, 3),
        "calmar_ratio": round(calmar_ratio, 3),
        "recovery_factor": round(recovery_factor, 3),
        "downside_deviation_pct": round(downside_dev_pct, 2),
        "sortino_ratio": round(sortino_ratio, 3),
        "burke_ratio": round(burke_ratio, 3),
        "time_underwater_pct": round(time_underwater_pct, 2),
        "avg_drawdown_pct": round(avg_drawdown_pct, 2),
        "max_drawdown_duration_trades": max_underwater,
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
            "avg_win_duration_min": 0.0,
            "avg_loss_duration_min": 0.0,
            "win_loss_duration_ratio": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "full_kelly_pct": 0.0,
            "half_kelly_pct": 0.0,
        }

    wins = []
    losses = []
    win_durations = []
    loss_durations = []
    draws = 0
    durations = []
    curr_win_streak = 0
    curr_loss_streak = 0
    max_win_streak = 0
    max_loss_streak = 0

    for t in trades:
        # Freqtrade trade profit percentage is typically in 'profit_ratio' (0.05 = 5%)
        profit = _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
        duration_min = _safe_float(t.get("trade_duration", t.get("duration", 0.0)))
        durations.append(duration_min)

        if profit > 1e-6:
            wins.append(profit * 100.0)
            win_durations.append(duration_min)
            curr_win_streak += 1
            curr_loss_streak = 0
            if curr_win_streak > max_win_streak:
                max_win_streak = curr_win_streak
        elif profit < -1e-6:
            losses.append(abs(profit * 100.0))
            loss_durations.append(duration_min)
            curr_loss_streak += 1
            curr_win_streak = 0
            if curr_loss_streak > max_loss_streak:
                max_loss_streak = curr_loss_streak
        else:
            draws += 1
            curr_win_streak = 0
            curr_loss_streak = 0

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
    avg_win_dur = (sum(win_durations) / len(win_durations)) if win_durations else 0.0
    avg_loss_dur = (sum(loss_durations) / len(loss_durations)) if loss_durations else 0.0
    win_loss_dur_ratio = (avg_win_dur / avg_loss_dur) if avg_loss_dur > 0 else (999.0 if avg_win_dur > 0 else 0.0)

    # Kelly Criterion calculation: f* = (p * b - q) / b = p - (1 - p) / b
    if total_trades > 0 and loss_count > 0 and avg_loss > 0:
        b = avg_win / avg_loss
        p = win_count / total_trades
        q = 1.0 - p
        if b > 1e-6:
            f_star = (p * b - q) / b
            full_k = max(0.0, min(1.0, f_star)) * 100.0
        else:
            full_k = 0.0
        half_k = full_k / 2.0
    elif total_trades > 0 and loss_count == 0 and win_count > 0:
        full_k = 100.0
        half_k = 50.0
    else:
        full_k = 0.0
        half_k = 0.0

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
        "avg_win_duration_min": round(avg_win_dur, 1),
        "avg_loss_duration_min": round(avg_loss_dur, 1),
        "win_loss_duration_ratio": round(win_loss_dur_ratio, 2),
        "max_consecutive_wins": max_win_streak,
        "max_consecutive_losses": max_loss_streak,
        "full_kelly_pct": round(full_k, 2),
        "half_kelly_pct": round(half_k, 2),
    }


def calculate_exit_reason_breakdown(
    trades: list[dict[str, Any]],
    sort_by: str | None = None,
    min_trades: int = 1,
) -> dict[str, dict[str, Any]]:
    """Group trade performance metrics by exit reason and custom exit tag."""
    if not trades:
        return {}

    groups: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        tag = t.get("exit_tag") or t.get("exit_reason") or "unknown"
        if not tag:
            tag = "unknown"
        groups.setdefault(str(tag), []).append(t)

    breakdown = {}
    for tag, t_list in sorted(groups.items()):
        count = len(t_list)
        if count < min_trades:
            continue

        wins = []
        losses = []
        durations = []
        profits = []
        for t in t_list:
            p = _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
            dur = _safe_float(t.get("trade_duration", t.get("duration", 0.0)))
            profits.append(p)
            durations.append(dur)
            if p > 1e-6:
                wins.append(p * 100.0)
            elif p < -1e-6:
                losses.append(abs(p * 100.0))

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / count) * 100.0 if count > 0 else 0.0
        total_profit_pct = sum(profits) * 100.0
        avg_profit_pct = (total_profit_pct / count) if count > 0 else 0.0
        avg_dur = (sum(durations) / count) if count > 0 else 0.0
        pf = (sum(wins) / sum(losses)) if sum(losses) > 0 else (999.0 if sum(wins) > 0 else 0.0)

        breakdown[tag] = {
            "trades": count,
            "wins": win_count,
            "losses": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "avg_profit_pct": round(avg_profit_pct, 2),
            "avg_duration_min": round(avg_dur, 1),
            "profit_factor": round(pf, 2),
        }

    sort_map = {
        "trades": "trades",
        "profit": "total_profit_pct",
        "total_profit_pct": "total_profit_pct",
        "win_rate": "win_rate_pct",
        "win_rate_pct": "win_rate_pct",
        "pf": "profit_factor",
        "profit_factor": "profit_factor",
    }
    actual_sort = sort_map.get(sort_by, sort_by) if sort_by else None
    if actual_sort and breakdown:
        breakdown = dict(sorted(breakdown.items(), key=lambda item: item[1].get(actual_sort, 0), reverse=True))

    return breakdown


def calculate_pair_performance_breakdown(
    trades: list[dict[str, Any]],
    sort_by: str | None = None,
    min_trades: int = 1,
) -> dict[str, dict[str, Any]]:
    """Group trade performance metrics by trading pair."""
    if not trades:
        return {}

    groups: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        pair = t.get("pair") or "Unknown"
        groups.setdefault(str(pair), []).append(t)

    breakdown = {}
    for pair, t_list in sorted(groups.items()):
        count = len(t_list)
        if count < min_trades:
            continue

        wins = []
        losses = []
        durations = []
        profits = []
        for t in t_list:
            p = _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
            dur = _safe_float(t.get("trade_duration", t.get("duration", 0.0)))
            profits.append(p)
            durations.append(dur)
            if p > 1e-6:
                wins.append(p * 100.0)
            elif p < -1e-6:
                losses.append(abs(p * 100.0))

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / count) * 100.0 if count > 0 else 0.0
        total_profit_pct = sum(profits) * 100.0
        avg_profit_pct = (total_profit_pct / count) if count > 0 else 0.0
        avg_dur = (sum(durations) / count) if count > 0 else 0.0
        pf = (sum(wins) / sum(losses)) if sum(losses) > 0 else (999.0 if sum(wins) > 0 else 0.0)

        breakdown[pair] = {
            "trades": count,
            "wins": win_count,
            "losses": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "avg_profit_pct": round(avg_profit_pct, 2),
            "avg_duration_min": round(avg_dur, 1),
            "profit_factor": round(pf, 2),
        }

    sort_map = {
        "trades": "trades",
        "profit": "total_profit_pct",
        "total_profit_pct": "total_profit_pct",
        "win_rate": "win_rate_pct",
        "win_rate_pct": "win_rate_pct",
        "pf": "profit_factor",
        "profit_factor": "profit_factor",
    }
    actual_sort = sort_map.get(sort_by, sort_by) if sort_by else None
    if actual_sort and breakdown:
        breakdown = dict(sorted(breakdown.items(), key=lambda item: item[1].get(actual_sort, 0), reverse=True))

    return breakdown


def parse_freqtrade_backtest_json(
    json_data: dict[str, Any],
    sort_by: str | None = None,
    min_trades: int = 1,
) -> dict[str, Any]:
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
        exit_breakdown = calculate_exit_reason_breakdown(trades, sort_by=sort_by, min_trades=min_trades)
        pair_breakdown = calculate_pair_performance_breakdown(trades, sort_by=sort_by, min_trades=min_trades)

        combined = {
            "strategy": strat_name,
            **trade_metrics,
            **dd_metrics,
            "exit_reasons": exit_breakdown,
            "pair_performance": pair_breakdown,
        }
        strategy_results[strat_name] = combined

    return strategy_results


def generate_markdown_report(analysis_results: dict[str, Any]) -> str:
    """Generate Markdown report for backtest quantitative analysis."""
    lines = [
        "# 📊 Freqtrade 전략 심층 퀀트 리스크 및 하방 위험 분석 보고서",
        "",
        "| 전략명 | 총 거래 | 승률 | 최대 연승/연패 | 손익비(P.F.) | 기대값(Trade Exp.) | 켈리 비율(Full/Half) | 최대낙폭(MDD) | 궤양지수(Ulcer Index) | 소르티노 비율 | 버크 비율(Burke) | 마틴 비율(UPI) | 칼마 비율 | 회복 계수 | 수중 기간(Underwater) | 최대 침체(거래) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for name, data in analysis_results.items():
        max_cw = data.get("max_consecutive_wins", 0)
        max_cl = data.get("max_consecutive_losses", 0)
        streak_str = f"{max_cw}승/{max_cl}패"
        full_k = data.get("full_kelly_pct", 0.0)
        half_k = data.get("half_kelly_pct", 0.0)
        kelly_str = f"{full_k:.1f}%/{half_k:.1f}%"
        lines.append(
            f"| **{name}** | {data['total_trades']}회 | {data['win_rate_pct']:.1f}% | {streak_str} | "
            f"{data['profit_factor']:.2f} | {data['expectancy_pct']:+.3f}% | {kelly_str} | "
            f"-{data['max_drawdown_pct']:.2f}% | {data['ulcer_index']:.2f}% | "
            f"{data.get('sortino_ratio', 0.0):.2f} | "
            f"{data.get('burke_ratio', 0.0):.2f} | "
            f"{data['martin_ratio']:.2f} | {data['calmar_ratio']:.2f} | "
            f"{data.get('recovery_factor', 0.0):.2f} | "
            f"{data.get('time_underwater_pct', 0.0):.1f}% | "
            f"{data.get('max_drawdown_duration_trades', 0)}회 |"
        )

    # Detailed exit reason tables
    for name, data in analysis_results.items():
        exits = data.get("exit_reasons", {})
        if exits:
            lines.append("")
            lines.append(f"### 🏷️ 전략 `{name}` 청산 사유 및 태그별 성과 분석")
            lines.append("| 청산 태그/사유 | 거래수 | 승률 | 총 수익률 | 평균 수익률 | 손익비(P.F.) | 평균 보유시간 |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
            for tag, s in exits.items():
                lines.append(
                    f"| `{tag}` | {s['trades']}회 | {s['win_rate_pct']:.1f}% | "
                    f"{s['total_profit_pct']:+.2f}% | {s['avg_profit_pct']:+.2f}% | "
                    f"{s['profit_factor']:.2f} | {s['avg_duration_min']:.1f}분 |"
                )

    # Detailed pair performance tables
    for name, data in analysis_results.items():
        pairs = data.get("pair_performance", {})
        if pairs:
            lines.append("")
            lines.append(f"### 🪙 전략 `{name}` 거래 페어별 성과 비교")
            lines.append("| 거래 페어 | 거래수 | 승률 | 총 수익률 | 평균 수익률 | 손익비(P.F.) | 평균 보유시간 |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
            for pair, s in pairs.items():
                lines.append(
                    f"| `{pair}` | {s['trades']}회 | {s['win_rate_pct']:.1f}% | "
                    f"{s['total_profit_pct']:+.2f}% | {s['avg_profit_pct']:+.2f}% | "
                    f"{s['profit_factor']:.2f} | {s['avg_duration_min']:.1f}분 |"
                )

    lines.append("")
    lines.append("### 💡 지표 설명 (Methodology)")
    lines.append("- **궤양지수 (Ulcer Index, Peter Martin 1987)**: 고점 대비 하락폭(Drawdown)의 제곱평균제곱근(RMS). 단순 변동성과 달리 상승 변동성은 처벌하지 않고 깊고 긴 하락장만을 집중 가중 처벌합니다.")
    lines.append("- **마틴 비율 (Martin Ratio / UPI)**: 총 수익률을 궤양지수로 나눈 값으로, 샤프 지수보다 추세추종 전략의 실질 하방 위험 대비 성과를 정확하게 평가합니다.")
    lines.append("- **소르티노 비율 (Sortino Ratio)**: 하방 변동성(Downside Deviation)만을 페널티로 부여하여 하방 손실 위험 대비 전략의 초과 수익률을 평가합니다.")
    lines.append("- **버크 비율 (Burke Ratio, Gibbons Burke 1994)**: 총 수익률을 개별 낙폭(Drawdown)들의 제곱합의 제곱근으로 나눈 비율로, 단일 극단값뿐 아니라 누적된 다수의 하락 충격을 종합 반영합니다.")
    lines.append("- **수중 기간 비율 (Time Underwater %)**: 전체 거래 중 최고점(High-Water Mark)을 탈환하지 못하고 손실 구간에 머무른 거래 수의 백분율입니다.")
    lines.append("- **켈리 비율 (Kelly Criterion, Full/Half)**: 승률과 손익비를 바탕으로 자본 성장을 극대화하는 이론적 최적 베팅 비중(f*) 및 암호화폐 시장의 꼬리 위험을 완화한 보수적 권장치인 하프 켈리(Half-Kelly, f*/2) 비율입니다.")
    lines.append("- **거래 기대값 (Trade Expectancy)**: (승률 × 평균 수익률) - (패율 × 평균 손실률). 1회 거래당 기대되는 통계적 엣지(Edge)입니다.")
    lines.append("- **청산 사유 분석 (Exit Breakdown)**: 각 커스텀 청산 태그(RSI 과매수, 손절, 익절 등)의 개별 승률과 평균 보유 기간을 분리 집계하여 취약한 청산 로직을 진단합니다.")
    lines.append("- **페어별 성과 분석 (Pair Performance)**: 거래 코인 페어별 승률, 누적 수익률, 손익비 및 보유시간을 비교하여 전략에 유리하거나 불리한 자산을 식별합니다.")
    lines.append("- **보유시간 비대칭도 (Win/Loss Duration Ratio)**: 수익 거래 평균 보유시간 / 손실 거래 평균 보유시간. 1.0 이상이면 손실을 빠르게 끊고 이익을 길게 가져가는(Let winners run, cut losers) 바람직한 추세추종 특성을 나타냅니다.")
    lines.append("- **회복 계수 (Recovery Factor)**: 총 순수익률을 최대 낙폭(MDD)으로 나눈 값으로, 감내한 최대 하방 위험 대비 얼마만큼의 자본 증식을 달성했는지 평가합니다.")
    lines.append("- **최대 침체 기간 (Max Underwater Trades)**: 고점 갱신 후 새로운 고점을 탈환하지 못하고 지속된 최장 연속 거래 횟수입니다.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze Freqtrade backtest results for Ulcer Index and Expectancy")
    parser.add_argument("file", type=str, help="Path to backtest-result.json file")
    parser.add_argument("--output", "-o", type=str, default=None, help="Optional output Markdown path")
    parser.add_argument("--json", "-j", type=str, default=None, help="Optional output JSON path for programmatic consumption")
    parser.add_argument(
        "--sort-by",
        type=str,
        default=None,
        choices=["trades", "profit", "win_rate", "pf"],
        help="Field to sort exit and pair breakdown tables by (trades, profit, win_rate, pf)",
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=1,
        help="Minimum trade count threshold for exit reason and pair tables (default: 1)",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        raise FileNotFoundError(f"Backtest result file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = parse_freqtrade_backtest_json(data, sort_by=args.sort_by, min_trades=args.min_trades)
    md_content = generate_markdown_report(results)

    if args.json:
        json_path = Path(args.json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"[+] Quant analysis JSON exported to: {json_path}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"[+] Quant analysis report exported to: {out_path}")
    elif not args.json:
        print(md_content)


if __name__ == "__main__":
    main()
