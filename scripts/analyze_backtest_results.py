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
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import random
import sys
from typing import Any
import zipfile

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass



def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert value to float, replacing NaN, Inf, or invalid types with default."""
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _percentile(values: list[float], pct: float) -> float:
    """Calculate percentile from a list of floats using standard linear interpolation."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return d0 + d1


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
            "romad_ratio": 0.0,
            "recovery_factor": 0.0,
            "downside_deviation_pct": 0.0,
            "sortino_ratio": 0.0,
            "burke_ratio": 0.0,
            "sterling_ratio": 0.0,
            "gain_to_pain_ratio": 0.0,
            "omega_ratio": 0.0,
            "k_ratio": 0.0,
            "time_underwater_pct": 0.0,
            "avg_drawdown_pct": 0.0,
            "max_drawdown_duration_trades": 0,
            "var_95_pct": 0.0,
            "cvar_95_pct": 0.0,
            "var_99_pct": 0.0,
            "cvar_99_pct": 0.0,
            "dar_95_pct": 0.0,
            "cdar_95_pct": 0.0,
            "cdar_ratio": 0.0,
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

    # Sterling Ratio = Total Return / Average Drawdown
    sterling_ratio = (
        (total_return_pct / avg_drawdown_pct)
        if avg_drawdown_pct > 1e-6
        else (999.0 if total_return_pct > 0 else 0.0)
    )

    # Gain-to-Pain Ratio (Jack Schwager) = Sum(All Returns) / Sum(|Negative Returns|)
    sum_all_profits = sum(clean_profits)
    sum_abs_loss = sum(abs(p) for p in clean_profits if p < 0.0)
    gain_to_pain_ratio = (
        (sum_all_profits / sum_abs_loss)
        if sum_abs_loss > 1e-6
        else (999.0 if sum_all_profits > 0 else 0.0)
    )

    # Keating-Shadwick Omega Ratio (threshold = 0.0) = Sum(Upside Gains) / Sum(|Downside Losses|)
    sum_upside_gains = sum(p for p in clean_profits if p > 0.0)
    omega_ratio = (
        (sum_upside_gains / sum_abs_loss)
        if sum_abs_loss > 1e-6
        else (999.0 if sum_upside_gains > 0 else 0.0)
    )

    # Pain Index = mean( |DD| )
    pain_index = sum(abs(dd) for dd in drawdowns_pct) / len(drawdowns_pct) if drawdowns_pct else 0.0

    # Martin Ratio = Total Return / Ulcer Index
    martin_ratio = (total_return_pct / ulcer_index) if ulcer_index > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

    # Pain Ratio = Total Return / Pain Index
    pain_ratio = (total_return_pct / pain_index) if pain_index > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

    # Calmar Ratio = Total Return / Max Drawdown
    calmar_ratio = (total_return_pct / mdd_pct) if mdd_pct > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

    # Return over Maximum Drawdown (RoMaD)
    romad_ratio = (total_return_pct / mdd_pct) if mdd_pct > 1e-6 else (999.0 if total_return_pct > 0 else 0.0)

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

    # K-Ratio (Lars Kestner) = Slope of equity curve / (Standard Error of slope * sqrt(T))
    T = len(drawdowns_pct)
    if T >= 3:
        cum_ret = [(val - 1.0) * 100.0 for val in equity[1:]]
        mean_t = (T - 1) / 2.0
        mean_y = sum(cum_ret) / T
        ss_xx = sum((t - mean_t) ** 2 for t in range(T))
        ss_xy = sum((t - mean_t) * (y - mean_y) for t, y in enumerate(cum_ret))
        if ss_xx > 1e-9:
            slope = ss_xy / ss_xx
            intercept = mean_y - slope * mean_t
            ss_res = sum((y - (intercept + slope * t)) ** 2 for t, y in enumerate(cum_ret))
            se_slope = math.sqrt(ss_res / ((T - 2) * ss_xx))
            if se_slope > 1e-9:
                k_ratio = slope / (se_slope * math.sqrt(T))
            else:
                k_ratio = 999.0 if slope > 0 else (-999.0 if slope < 0 else 0.0)
        else:
            k_ratio = 0.0
    else:
        k_ratio = 0.0

    # Historical Value-at-Risk (VaR) and Conditional Value-at-Risk (CVaR / Expected Shortfall)
    # VaR 95% = 5th percentile of single-trade return
    var_95 = _percentile(clean_profits, 5.0)
    var_95_pct = var_95 * 100.0
    tail_95 = [p * 100.0 for p in clean_profits if p <= var_95]
    cvar_95_pct = (sum(tail_95) / len(tail_95)) if tail_95 else var_95_pct

    # VaR 99% = 1st percentile of single-trade return
    var_99 = _percentile(clean_profits, 1.0)
    var_99_pct = var_99 * 100.0
    tail_99 = [p * 100.0 for p in clean_profits if p <= var_99]
    cvar_99_pct = (sum(tail_99) / len(tail_99)) if tail_99 else var_99_pct

    # Drawdown-at-Risk (DaR 95%) and Conditional Drawdown-at-Risk (CDaR 95% / Chekhlov, Uryasev, Zabarankin)
    dd_depths = [abs(dd) for dd in drawdowns_pct]
    dar_95_pct = _percentile(dd_depths, 95.0) if dd_depths else 0.0
    tail_dar_95 = [d for d in dd_depths if d >= dar_95_pct]
    cdar_95_pct = (sum(tail_dar_95) / len(tail_dar_95)) if tail_dar_95 else dar_95_pct
    cdar_ratio = (
        (total_return_pct / cdar_95_pct)
        if cdar_95_pct > 1e-6
        else (999.0 if total_return_pct > 0 else 0.0)
    )

    return {
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(mdd_pct, 2),
        "ulcer_index": round(ulcer_index, 3),
        "pain_index": round(pain_index, 3),
        "martin_ratio": round(martin_ratio, 3),
        "pain_ratio": round(pain_ratio, 3),
        "calmar_ratio": round(calmar_ratio, 3),
        "romad_ratio": round(romad_ratio, 3),
        "recovery_factor": round(recovery_factor, 3),
        "downside_deviation_pct": round(downside_dev_pct, 2),
        "sortino_ratio": round(sortino_ratio, 3),
        "burke_ratio": round(burke_ratio, 3),
        "sterling_ratio": round(sterling_ratio, 3),
        "gain_to_pain_ratio": round(gain_to_pain_ratio, 3),
        "omega_ratio": round(omega_ratio, 3),
        "k_ratio": round(k_ratio, 3),
        "time_underwater_pct": round(time_underwater_pct, 2),
        "avg_drawdown_pct": round(avg_drawdown_pct, 2),
        "max_drawdown_duration_trades": max_underwater,
        "var_95_pct": round(var_95_pct, 2),
        "cvar_95_pct": round(cvar_95_pct, 2),
        "var_99_pct": round(var_99_pct, 2),
        "cvar_99_pct": round(cvar_99_pct, 2),
        "dar_95_pct": round(dar_95_pct, 2),
        "cdar_95_pct": round(cdar_95_pct, 2),
        "cdar_ratio": round(cdar_ratio, 3),
    }


def calculate_annualized_metrics(
    trades: list[dict[str, Any]],
    total_return_pct: float,
    max_drawdown_pct: float,
    backtest_days: float | None = None,
    backtest_start_ts: int | float | None = None,
    backtest_end_ts: int | float | None = None,
) -> dict[str, Any]:
    """Calculate CAGR, Annualized Sharpe, and Annualized Calmar ratios.

    Determines period length from backtest metadata or trade open/close timestamps.
    """
    days = 0.0
    if backtest_days is not None and backtest_days > 0:
        days = float(backtest_days)
    elif (
        backtest_start_ts is not None
        and backtest_end_ts is not None
        and backtest_end_ts > backtest_start_ts
    ):
        diff_s = float(backtest_end_ts - backtest_start_ts)
        if diff_s > 1e11:
            diff_s /= 1000.0
        days = diff_s / 86400.0
    elif trades:
        timestamps: list[datetime] = []
        for t in trades:
            for key in ("open_date", "close_date"):
                d_val = t.get(key)
                if isinstance(d_val, str) and d_val.strip():
                    try:
                        clean_d = d_val.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(clean_d)
                        timestamps.append(dt)
                    except Exception:
                        pass
            for key in ("open_timestamp", "close_timestamp"):
                ts_val = t.get(key)
                if ts_val is not None and ts_val > 0:
                    try:
                        sec = ts_val / 1000.0 if ts_val > 1e11 else float(ts_val)
                        dt = datetime.fromtimestamp(sec, timezone.utc)
                        timestamps.append(dt)
                    except Exception:
                        pass
        if len(timestamps) >= 2:
            min_dt = min(timestamps)
            max_dt = max(timestamps)
            span_s = (max_dt - min_dt).total_seconds()
            if span_s > 0:
                days = span_s / 86400.0

    if days <= 0.0:
        return {
            "backtest_days": 0.0,
            "cagr_pct": round(total_return_pct, 2),
            "annualized_sharpe": 0.0,
            "annualized_calmar": 0.0,
            "mar_ratio": 0.0,
        }

    years = days / 365.25
    tot_ret_decimal = total_return_pct / 100.0
    if 1.0 + tot_ret_decimal > 0:
        cagr = ((1.0 + tot_ret_decimal) ** (1.0 / years) - 1.0) * 100.0
    else:
        cagr = -100.0

    mdd = abs(max_drawdown_pct)
    if mdd > 1e-6:
        annualized_calmar = cagr / mdd
        mar_ratio = cagr / mdd
    else:
        annualized_calmar = 999.0 if cagr > 0 else 0.0
        mar_ratio = 999.0 if cagr > 0 else 0.0

    total_trades = len(trades)
    if total_trades > 0 and years > 0:
        trades_per_year = total_trades / years
        profits = [
            _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
            for t in trades
        ]
        mean_p = sum(profits) / total_trades
        variance = sum((p - mean_p) ** 2 for p in profits) / total_trades
        std_p = math.sqrt(variance)
        if std_p > 1e-9:
            annualized_sharpe = (mean_p / std_p) * math.sqrt(trades_per_year)
        else:
            annualized_sharpe = 999.0 if mean_p > 0 else 0.0
    else:
        annualized_sharpe = 0.0

    return {
        "backtest_days": round(days, 1),
        "cagr_pct": round(cagr, 2),
        "annualized_sharpe": round(annualized_sharpe, 2),
        "annualized_calmar": round(annualized_calmar, 2),
        "mar_ratio": round(mar_ratio, 2),
    }


def calculate_risk_of_ruin(
    win_rate: float,
    payoff_ratio: float,
    bet_fraction: float = 0.02,
    loss_limit: float = 0.5,
) -> float:
    """Calculate theoretical Risk of Ruin (Ralph Vince & Perry Kaufman formula).

    Evaluates the probability of suffering an accumulated drawdown of loss_limit
    (e.g., 0.5 for a 50% account drawdown) before reaching capital growth targets.
    """
    if not (0.0 < win_rate < 1.0) or payoff_ratio <= 0.0 or not (0.0 < bet_fraction <= 1.0) or not (0.0 < loss_limit <= 1.0):
        return 1.0 if (win_rate <= 0.0 or payoff_ratio <= 0.0) else 0.0

    loss_rate = 1.0 - win_rate
    expected_payoff = win_rate * payoff_ratio - loss_rate
    if expected_payoff <= 0.0:
        return 1.0

    denom = win_rate * payoff_ratio + loss_rate
    if denom <= 1e-9:
        return 1.0

    edge = expected_payoff / denom
    z = (1.0 - edge) / (1.0 + edge)

    units = loss_limit / bet_fraction
    ror = float(z ** units)
    return max(0.0, min(1.0, ror))


def simulate_monte_carlo_drawdown(
    trades: list[dict[str, Any]] | list[float],
    iterations: int = 1000,
    threshold_mdd_pct: float = 20.0,
    seed: int | None = 42,
) -> dict[str, Any]:
    """Run Monte Carlo trade permutation simulation to evaluate sequence risk and stress drawdowns.

    Parameters
    ----------
    trades : list[dict[str, Any]] | list[float]
        List of trade dictionaries or float profit fractions.
    iterations : int
        Number of resampled permutations (default: 1000).
    threshold_mdd_pct : float
        Drawdown threshold to evaluate exceedance probability (default: 20.0%).
    seed : int | None
        Random seed for deterministic reproducibility.

    Returns
    -------
    dict[str, Any]
        Monte Carlo risk metrics including mean, median, 95% worst-case, 99% stress
        max drawdowns, and ruin/exceedance probability.
    """
    if not trades or iterations < 1:
        return {
            "mc_iterations": max(0, iterations),
            "mc_mdd_mean_pct": 0.0,
            "mc_mdd_median_pct": 0.0,
            "mc_mdd_95_pct": 0.0,
            "mc_mdd_99_pct": 0.0,
            "mc_mdd_max_pct": 0.0,
            "mc_ruin_threshold_pct": round(float(threshold_mdd_pct), 1),
            "mc_prob_mdd_exceed_pct": 0.0,
        }

    clean_profits: list[float] = []
    for item in trades:
        if isinstance(item, dict):
            clean_profits.append(
                _safe_float(item.get("profit_ratio", item.get("profit_pct", 0.0) / 100.0 if "profit_pct" in item else 0.0))
            )
        else:
            clean_profits.append(_safe_float(item))

    if len(clean_profits) < 2:
        return {
            "mc_iterations": iterations,
            "mc_mdd_mean_pct": 0.0,
            "mc_mdd_median_pct": 0.0,
            "mc_mdd_95_pct": 0.0,
            "mc_mdd_99_pct": 0.0,
            "mc_mdd_max_pct": 0.0,
            "mc_ruin_threshold_pct": round(float(threshold_mdd_pct), 1),
            "mc_prob_mdd_exceed_pct": 0.0,
        }

    rng = random.Random(seed) if seed is not None else random.Random()
    sim_mdds: list[float] = []
    threshold_val = float(threshold_mdd_pct)
    pool = list(clean_profits)

    for _ in range(iterations):
        shuffled = list(pool)
        rng.shuffle(shuffled)
        equity = 1.0
        peak = 1.0
        worst_dd = 0.0
        for p in shuffled:
            equity *= (1.0 + p)
            if equity > peak:
                peak = equity
            dd = (equity - peak) / peak * 100.0
            if dd < worst_dd:
                worst_dd = dd
        sim_mdds.append(abs(worst_dd))

    sim_mdds.sort()
    n = len(sim_mdds)
    mc_mdd_mean = sum(sim_mdds) / n if n > 0 else 0.0
    mc_mdd_median = _percentile(sim_mdds, 50.0) if n > 0 else 0.0
    mc_mdd_95 = _percentile(sim_mdds, 95.0) if n > 0 else 0.0
    mc_mdd_99 = _percentile(sim_mdds, 99.0) if n > 0 else 0.0
    mc_mdd_max = max(sim_mdds) if sim_mdds else 0.0
    exceed_count = sum(1 for m in sim_mdds if m >= threshold_val)
    prob_exceed = (exceed_count / n * 100.0) if n > 0 else 0.0

    return {
        "mc_iterations": iterations,
        "mc_mdd_mean_pct": round(mc_mdd_mean, 2),
        "mc_mdd_median_pct": round(mc_mdd_median, 2),
        "mc_mdd_95_pct": round(mc_mdd_95, 2),
        "mc_mdd_99_pct": round(mc_mdd_99, 2),
        "mc_mdd_max_pct": round(mc_mdd_max, 2),
        "mc_ruin_threshold_pct": round(threshold_val, 1),
        "mc_prob_mdd_exceed_pct": round(prob_exceed, 2),
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
            "win_loss_count_ratio": 0.0,
            "expectancy_bps": 0.0,
            "avg_duration_min": 0.0,
            "avg_win_duration_min": 0.0,
            "avg_loss_duration_min": 0.0,
            "win_loss_duration_ratio": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "streak_ratio": 0.0,
            "cpc_index": 0.0,
            "runs_test_zscore": 0.0,
            "runs_test_rating": "N/A",
            "full_kelly_pct": 0.0,
            "half_kelly_pct": 0.0,
            "risk_of_ruin_pct": 0.0,
            "tail_ratio": 0.0,
            "common_sense_ratio": 0.0,
            "sqn": 0.0,
            "sqn_100": 0.0,
            "sqn_rating": "N/A",
            "skewness": 0.0,
            "kurtosis": 0.0,
            "max_win_pct": 0.0,
            "max_loss_pct": 0.0,
            "std_profit_pct": 0.0,
            "median_profit_pct": 0.0,
            "p25_profit_pct": 0.0,
            "p75_profit_pct": 0.0,
            "iqr_profit_pct": 0.0,
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
    outcomes: list[int] = []

    for t in trades:
        # Freqtrade trade profit percentage is typically in 'profit_ratio' (0.05 = 5%)
        profit = _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
        duration_min = _safe_float(t.get("trade_duration", t.get("duration", 0.0)))
        durations.append(duration_min)

        if profit > 1e-6:
            wins.append(profit * 100.0)
            win_durations.append(duration_min)
            outcomes.append(1)
            curr_win_streak += 1
            curr_loss_streak = 0
            if curr_win_streak > max_win_streak:
                max_win_streak = curr_win_streak
        elif profit < -1e-6:
            losses.append(abs(profit * 100.0))
            loss_durations.append(duration_min)
            outcomes.append(-1)
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
    win_loss_count_ratio = (win_count / loss_count) if loss_count > 0 else (999.0 if win_count > 0 else 0.0)

    # Expectancy = (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
    p_win = win_count / total_trades if total_trades > 0 else 0.0
    p_loss = loss_count / total_trades if total_trades > 0 else 0.0
    expectancy = (p_win * avg_win) - (p_loss * avg_loss)
    expectancy_bps = round(expectancy * 100.0, 1)

    avg_duration = sum(durations) / len(durations) if durations else 0.0
    avg_win_dur = (sum(win_durations) / len(win_durations)) if win_durations else 0.0
    avg_loss_dur = (sum(loss_durations) / len(loss_durations)) if loss_durations else 0.0
    win_loss_dur_ratio = (avg_win_dur / avg_loss_dur) if avg_loss_dur > 0 else (999.0 if avg_win_dur > 0 else 0.0)

    # Kelly Criterion calculation: f* = (p * b - q) / b = p - (1 - p) / b
    b = 0.0
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

    # Risk of Ruin (50% account drawdown barrier, Ralph Vince & Perry Kaufman)
    if total_trades > 0 and loss_count > 0 and avg_loss > 0 and b > 1e-6:
        p = win_count / total_trades
        frac = (half_k / 100.0) if half_k > 0 else 0.02
        ror = calculate_risk_of_ruin(win_rate=p, payoff_ratio=b, bet_fraction=frac, loss_limit=0.5)
        risk_of_ruin_pct = ror * 100.0
    elif total_trades > 0 and loss_count == 0 and win_count > 0:
        risk_of_ruin_pct = 0.0
    else:
        risk_of_ruin_pct = 100.0 if total_trades > 0 else 0.0

    # Streak Asymmetry Ratio = max_consecutive_wins / max_consecutive_losses
    streak_ratio = (
        (max_win_streak / max_loss_streak)
        if max_loss_streak > 0
        else (999.0 if max_win_streak > 0 else 0.0)
    )

    # CPC Index (Continuation Protection Criterion) = Profit Factor * (Win Rate / 100) * Win/Loss Ratio
    p_w = win_rate / 100.0
    cpc_index = (profit_factor * p_w * win_loss_ratio) if (profit_factor > 0 and win_loss_ratio > 0) else 0.0

    # Wald-Wolfowitz Runs Test for Trade Serial Independence (Perry Kaufman)
    runs = 1 if outcomes else 0
    for i in range(1, len(outcomes)):
        if outcomes[i] != outcomes[i - 1]:
            runs += 1

    n_w = len(wins)
    n_l = len(losses)
    n_total = n_w + n_l
    if n_total >= 3 and n_w > 0 and n_l > 0:
        expected_runs = (2.0 * n_w * n_l / n_total) + 1.0
        var_runs = (2.0 * n_w * n_l * (2.0 * n_w * n_l - n_total)) / ((n_total ** 2) * (n_total - 1))
        if var_runs > 1e-9:
            runs_z = (runs - expected_runs) / math.sqrt(var_runs)
        else:
            runs_z = 0.0
        if runs_z < -1.96:
            runs_rating = "Clustering (Streaks)"
        elif runs_z > 1.96:
            runs_rating = "Alternating (Mean-Rev)"
        else:
            runs_rating = "Independent (Random)"
    else:
        runs_z = 0.0
        runs_rating = "N/A"

    # Tail Ratio (p95 / |p05|) and Common Sense Ratio (CSR = Profit Factor * Tail Ratio)
    all_trade_profits_pct = [
        _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0)) * 100.0
        for t in trades
    ]
    tail_ratio = 0.0
    common_sense_ratio = 0.0
    if len(all_trade_profits_pct) >= 2:
        p95 = _percentile(all_trade_profits_pct, 95.0)
        p05 = _percentile(all_trade_profits_pct, 5.0)
        abs_p05 = abs(p05)
        tail_ratio = (p95 / abs_p05) if abs_p05 > 1e-6 else (999.0 if p95 > 0 else 0.0)
        common_sense_ratio = (profit_factor * tail_ratio) if (profit_factor > 0 and tail_ratio > 0) else 0.0
    # Van Tharp System Quality Number (SQN)
    N = len(all_trade_profits_pct)
    if N >= 2:
        mean_pnl = sum(all_trade_profits_pct) / N
        var_pnl = sum((x - mean_pnl) ** 2 for x in all_trade_profits_pct) / (N - 1)
        std_pnl = math.sqrt(var_pnl)
        if std_pnl > 1e-6:
            sqn = math.sqrt(N) * (mean_pnl / std_pnl)
            sqn_100 = math.sqrt(min(N, 100)) * (mean_pnl / std_pnl)
        else:
            sqn = 999.0 if mean_pnl > 0 else (-999.0 if mean_pnl < 0 else 0.0)
            sqn_100 = sqn
    else:
        sqn = 0.0
        sqn_100 = 0.0

    if sqn >= 7.0:
        sqn_rating = "Holy Grail"
    elif sqn >= 5.0:
        sqn_rating = "Superb"
    elif sqn >= 3.0:
        sqn_rating = "Excellent"
    elif sqn >= 2.5:
        sqn_rating = "Good"
    elif sqn >= 2.0:
        sqn_rating = "Average"
    elif sqn >= 1.6:
        sqn_rating = "Below Average"
    else:
        sqn_rating = "Poor"

    # Skewness and Excess Kurtosis of trade returns distribution
    if N >= 3 and std_pnl > 1e-6:
        m3_sum = sum(((x - mean_pnl) / std_pnl) ** 3 for x in all_trade_profits_pct)
        skewness = (N / ((N - 1) * (N - 2))) * m3_sum
    else:
        skewness = 0.0

    if N >= 4 and std_pnl > 1e-6:
        m4_sum = sum(((x - mean_pnl) / std_pnl) ** 4 for x in all_trade_profits_pct)
        c1 = (N * (N + 1)) / ((N - 1) * (N - 2) * (N - 3))
        c2 = (3.0 * ((N - 1) ** 2)) / ((N - 2) * (N - 3))
        kurtosis = (c1 * m4_sum) - c2
    else:
        kurtosis = 0.0

    max_win = max(wins) if wins else 0.0
    max_loss = max(losses) if losses else 0.0
    std_profit = std_pnl if N >= 2 else 0.0

    if len(all_trade_profits_pct) >= 2:
        median_pnl = _percentile(all_trade_profits_pct, 50.0)
        p25_pnl = _percentile(all_trade_profits_pct, 25.0)
        p75_pnl = _percentile(all_trade_profits_pct, 75.0)
        iqr_pnl = p75_pnl - p25_pnl
    elif len(all_trade_profits_pct) == 1:
        median_pnl = all_trade_profits_pct[0]
        p25_pnl = median_pnl
        p75_pnl = median_pnl
        iqr_pnl = 0.0
    else:
        median_pnl = 0.0
        p25_pnl = 0.0
        p75_pnl = 0.0
        iqr_pnl = 0.0

    return {
        "total_trades": total_trades,
        "wins": win_count,
        "losses": loss_count,
        "draws": draws,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_pct": round(expectancy, 3),
        "expectancy_bps": expectancy_bps,
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "win_loss_ratio": round(win_loss_ratio, 2),
        "win_loss_count_ratio": round(win_loss_count_ratio, 2),
        "avg_duration_min": round(avg_duration, 1),
        "avg_win_duration_min": round(avg_win_dur, 1),
        "avg_loss_duration_min": round(avg_loss_dur, 1),
        "win_loss_duration_ratio": round(win_loss_dur_ratio, 2),
        "max_consecutive_wins": max_win_streak,
        "max_consecutive_losses": max_loss_streak,
        "streak_ratio": round(streak_ratio, 2),
        "cpc_index": round(cpc_index, 2),
        "runs_test_zscore": round(runs_z, 2),
        "runs_test_rating": runs_rating,
        "full_kelly_pct": round(full_k, 2),
        "half_kelly_pct": round(half_k, 2),
        "risk_of_ruin_pct": round(risk_of_ruin_pct, 2),
        "tail_ratio": round(tail_ratio, 2),
        "common_sense_ratio": round(common_sense_ratio, 2),
        "sqn": round(sqn, 2),
        "sqn_100": round(sqn_100, 2),
        "sqn_rating": sqn_rating,
        "skewness": round(skewness, 3),
        "kurtosis": round(kurtosis, 3),
        "max_win_pct": round(max_win, 2),
        "max_loss_pct": round(max_loss, 2),
        "std_profit_pct": round(std_profit, 2),
        "median_profit_pct": round(median_pnl, 2),
        "p25_profit_pct": round(p25_pnl, 2),
        "p75_profit_pct": round(p75_pnl, 2),
        "iqr_profit_pct": round(iqr_pnl, 2),
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
        avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
        avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
        p_win = win_count / count if count > 0 else 0.0
        p_loss = loss_count / count if count > 0 else 0.0
        exp_pct = (p_win * avg_win) - (p_loss * avg_loss)
        exp_bps = round(exp_pct * 100.0, 1)
        max_win = max(wins) if wins else 0.0
        max_loss = max(losses) if losses else 0.0

        breakdown[tag] = {
            "trades": count,
            "wins": win_count,
            "losses": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "avg_profit_pct": round(avg_profit_pct, 2),
            "avg_duration_min": round(avg_dur, 1),
            "profit_factor": round(pf, 2),
            "expectancy_bps": exp_bps,
            "max_win_pct": round(max_win, 2),
            "max_loss_pct": round(max_loss, 2),
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
        avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
        avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
        p_win = win_count / count if count > 0 else 0.0
        p_loss = loss_count / count if count > 0 else 0.0
        exp_pct = (p_win * avg_win) - (p_loss * avg_loss)
        exp_bps = round(exp_pct * 100.0, 1)
        max_win = max(wins) if wins else 0.0
        max_loss = max(losses) if losses else 0.0

        breakdown[pair] = {
            "trades": count,
            "wins": win_count,
            "losses": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "avg_profit_pct": round(avg_profit_pct, 2),
            "avg_duration_min": round(avg_dur, 1),
            "profit_factor": round(pf, 2),
            "expectancy_bps": exp_bps,
            "max_win_pct": round(max_win, 2),
            "max_loss_pct": round(max_loss, 2),
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


def calculate_direction_breakdown(
    trades: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Group trade performance metrics by direction (long vs short)."""
    if not trades:
        return {}

    groups: dict[str, list[dict[str, Any]]] = {"long": [], "short": []}
    for t in trades:
        is_short = (
            t.get("is_short") is True
            or str(t.get("trade_direction", "")).lower() == "short"
            or str(t.get("direction", "")).lower() == "short"
        )
        side = "short" if is_short else "long"
        groups[side].append(t)

    breakdown: dict[str, dict[str, Any]] = {}
    for side, t_list in groups.items():
        count = len(t_list)
        if count == 0:
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
        avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
        avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
        p_win = win_count / count if count > 0 else 0.0
        p_loss = loss_count / count if count > 0 else 0.0
        exp_pct = (p_win * avg_win) - (p_loss * avg_loss)
        exp_bps = round(exp_pct * 100.0, 1)
        win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)
        max_win = max(wins) if wins else 0.0
        max_loss = max(losses) if losses else 0.0

        breakdown[side] = {
            "trades": count,
            "wins": win_count,
            "losses": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "avg_profit_pct": round(avg_profit_pct, 2),
            "avg_duration_min": round(avg_dur, 1),
            "profit_factor": round(pf, 2),
            "expectancy_bps": exp_bps,
            "win_loss_ratio": round(win_loss_ratio, 2),
            "max_win_pct": round(max_win, 2),
            "max_loss_pct": round(max_loss, 2),
        }

    return breakdown


def calculate_day_of_week_breakdown(
    trades: list[dict[str, Any]],
    sort_by: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Group trade performance metrics by day of the week (Monday through Sunday)."""
    if not trades:
        return {}

    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    groups: dict[str, list[dict[str, Any]]] = {d: [] for d in DAY_NAMES}

    for t in trades:
        dt: datetime | None = None
        for key in ("open_date", "close_date"):
            val = t.get(key)
            if isinstance(val, str) and val.strip():
                try:
                    clean = val.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(clean)
                    break
                except Exception:
                    pass
        if dt is None:
            for key in ("open_timestamp", "close_timestamp"):
                ts = t.get(key)
                if isinstance(ts, (int, float)) and ts > 0:
                    try:
                        sec = ts / 1000.0 if ts > 1e11 else float(ts)
                        dt = datetime.fromtimestamp(sec, timezone.utc)
                        break
                    except Exception:
                        pass
        if dt is not None:
            day_name = DAY_NAMES[dt.weekday()]
            groups[day_name].append(t)

    breakdown: dict[str, dict[str, Any]] = {}
    for day in DAY_NAMES:
        t_list = groups[day]
        count = len(t_list)
        if count == 0:
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
        avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
        avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
        p_win = win_count / count if count > 0 else 0.0
        p_loss = loss_count / count if count > 0 else 0.0
        exp_pct = (p_win * avg_win) - (p_loss * avg_loss)

        breakdown[day] = {
            "trades": count,
            "wins": win_count,
            "losses": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "avg_profit_pct": round(avg_profit_pct, 2),
            "avg_duration_min": round(avg_dur, 1),
            "profit_factor": round(pf, 2),
            "expectancy_bps": round(exp_pct * 100.0, 1),
            "max_win_pct": round(max(wins), 2) if wins else 0.0,
            "max_loss_pct": round(max(losses), 2) if losses else 0.0,
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


def calculate_hourly_breakdown(
    trades: list[dict[str, Any]],
    sort_by: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Group trade performance metrics by entry hour in UTC (00:00 to 23:00)."""
    if not trades:
        return {}

    groups: dict[str, list[dict[str, Any]]] = {f"{h:02d}:00 UTC": [] for h in range(24)}

    for t in trades:
        dt: datetime | None = None
        for key in ("open_date", "close_date"):
            val = t.get(key)
            if isinstance(val, str) and val.strip():
                try:
                    clean = val.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(clean)
                    break
                except Exception:
                    pass
        if dt is None:
            for key in ("open_timestamp", "close_timestamp"):
                ts = t.get(key)
                if isinstance(ts, (int, float)) and ts > 0:
                    try:
                        sec = ts / 1000.0 if ts > 1e11 else float(ts)
                        dt = datetime.fromtimestamp(sec, timezone.utc)
                        break
                    except Exception:
                        pass
        if dt is not None:
            hour_key = f"{dt.hour:02d}:00 UTC"
            groups[hour_key].append(t)

    breakdown: dict[str, dict[str, Any]] = {}
    for hour_key, t_list in groups.items():
        count = len(t_list)
        if count == 0:
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
        avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
        avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
        p_win = win_count / count if count > 0 else 0.0
        p_loss = loss_count / count if count > 0 else 0.0
        exp_pct = (p_win * avg_win) - (p_loss * avg_loss)
        wl_ratio = (avg_win / avg_loss) if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)

        breakdown[hour_key] = {
            "trades": count,
            "wins": win_count,
            "losses": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "avg_profit_pct": round(avg_profit_pct, 2),
            "avg_duration_min": round(avg_dur, 1),
            "profit_factor": round(pf, 2),
            "win_loss_ratio": round(wl_ratio, 2),
            "expectancy_bps": round(exp_pct * 100.0, 1),
            "max_win_pct": round(max(wins), 2) if wins else 0.0,
            "max_loss_pct": round(max(losses), 2) if losses else 0.0,
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


def calculate_duration_tier_breakdown(
    trades: list[dict[str, Any]],
    sort_by: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Group trade performance metrics by position holding duration tiers."""
    if not trades:
        return {}

    TIER_DEFINITIONS = [
        ("< 15m (Scalp)", 0.0, 15.0),
        ("15m - 1h (Short)", 15.0, 60.0),
        ("1h - 4h (Intraday)", 60.0, 240.0),
        ("4h - 24h (Swing)", 240.0, 1440.0),
        ("> 24h (Position)", 1440.0, float("inf")),
    ]

    groups: dict[str, list[dict[str, Any]]] = {tier[0]: [] for tier in TIER_DEFINITIONS}

    for t in trades:
        dur = _safe_float(t.get("trade_duration", t.get("duration", 0.0)))
        for tier_name, min_d, max_d in TIER_DEFINITIONS:
            if min_d <= dur < max_d:
                groups[tier_name].append(t)
                break

    breakdown: dict[str, dict[str, Any]] = {}
    for tier_name, _, _ in TIER_DEFINITIONS:
        t_list = groups[tier_name]
        count = len(t_list)
        if count == 0:
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
        avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
        avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
        p_win = win_count / count if count > 0 else 0.0
        p_loss = loss_count / count if count > 0 else 0.0
        exp_pct = (p_win * avg_win) - (p_loss * avg_loss)
        wl_ratio = (avg_win / avg_loss) if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)

        breakdown[tier_name] = {
            "trades": count,
            "wins": win_count,
            "losses": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "avg_profit_pct": round(avg_profit_pct, 2),
            "avg_duration_min": round(avg_dur, 1),
            "profit_factor": round(pf, 2),
            "win_loss_ratio": round(wl_ratio, 2),
            "expectancy_bps": round(exp_pct * 100.0, 1),
            "max_win_pct": round(max(wins), 2) if wins else 0.0,
            "max_loss_pct": round(max(losses), 2) if losses else 0.0,
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


def calculate_monthly_breakdown(
    trades: list[dict[str, Any]],
    sort_by: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Group trade performance metrics chronologically by calendar month (YYYY-MM)."""
    if not trades:
        return {}

    groups: dict[str, list[dict[str, Any]]] = {}

    for t in trades:
        dt: datetime | None = None
        for key in ("open_date", "close_date"):
            val = t.get(key)
            if isinstance(val, str) and val.strip():
                try:
                    clean = val.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(clean)
                    break
                except Exception:
                    pass
        if dt is None:
            for key in ("open_timestamp", "close_timestamp"):
                ts = t.get(key)
                if isinstance(ts, (int, float)) and ts > 0:
                    try:
                        sec = ts / 1000.0 if ts > 1e11 else float(ts)
                        dt = datetime.fromtimestamp(sec, timezone.utc)
                        break
                    except Exception:
                        pass
        if dt is not None:
            month_key = dt.strftime("%Y-%m")
            if month_key not in groups:
                groups[month_key] = []
            groups[month_key].append(t)

    sorted_months = sorted(groups.keys())
    breakdown: dict[str, dict[str, Any]] = {}

    for month_key in sorted_months:
        t_list = groups[month_key]
        count = len(t_list)
        if count == 0:
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
        avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
        avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
        p_win = win_count / count if count > 0 else 0.0
        p_loss = loss_count / count if count > 0 else 0.0
        exp_pct = (p_win * avg_win) - (p_loss * avg_loss)
        wl_ratio = (avg_win / avg_loss) if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)

        # Intra-month peak-to-trough max drawdown
        eq = [1.0]
        for p in profits:
            eq.append(eq[-1] * (1.0 + p))
        peak = eq[0]
        max_dd = 0.0
        for val in eq:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        breakdown[month_key] = {
            "trades": count,
            "wins": win_count,
            "losses": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "avg_profit_pct": round(avg_profit_pct, 2),
            "avg_duration_min": round(avg_dur, 1),
            "profit_factor": round(pf, 2),
            "win_loss_ratio": round(wl_ratio, 2),
            "expectancy_bps": round(exp_pct * 100.0, 1),
            "max_drawdown_pct": round(max_dd * 100.0, 2),
            "max_win_pct": round(max(wins), 2) if wins else 0.0,
            "max_loss_pct": round(max(losses), 2) if losses else 0.0,
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


def calculate_drawdown_episodes(
    trades: list[dict[str, Any]],
    top_n: int = 5,
) -> dict[str, Any]:
    """Identify distinct drawdown episodes, peak-to-trough decline, and recovery duration."""
    if not trades:
        return {
            "total_episodes": 0,
            "avg_recovery_trades": 0.0,
            "max_recovery_trades": 0,
            "avg_drawdown_trades": 0.0,
            "worst_dd_depth_pct": 0.0,
            "worst_dd_trades": 0,
            "current_is_recovered": True,
            "top_episodes": [],
        }

    equity = 1.0
    peak = 1.0
    peak_idx = -1
    peak_date = str(trades[0].get("open_date", "-"))

    trough = 1.0
    trough_idx = -1
    trough_date = str(trades[0].get("close_date", trades[0].get("open_date", "-")))

    episodes = []

    for i, t in enumerate(trades):
        p = _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
        c_date = str(t.get("close_date", t.get("open_date", f"Trade-{i+1}")))
        equity *= (1.0 + p)

        if equity >= peak * (1.0 - 1e-9):
            if trough < peak * (1.0 - 1e-6):
                dd_pct = (peak - trough) / peak * 100.0
                dd_trades = max(1, trough_idx - peak_idx)
                rec_trades = max(1, i - trough_idx)
                episodes.append({
                    "peak_date": peak_date,
                    "trough_date": trough_date,
                    "recovery_date": c_date,
                    "depth_pct": round(dd_pct, 2),
                    "drawdown_trades": dd_trades,
                    "recovery_trades": rec_trades,
                    "total_trades": dd_trades + rec_trades,
                    "is_recovered": True,
                })
            peak = equity
            peak_idx = i
            peak_date = c_date
            trough = equity
            trough_idx = i
            trough_date = c_date
        else:
            if equity < trough:
                trough = equity
                trough_idx = i
                trough_date = c_date

    if trough < peak * (1.0 - 1e-6):
        dd_pct = (peak - trough) / peak * 100.0
        dd_trades = max(1, trough_idx - peak_idx)
        rec_trades = max(0, len(trades) - 1 - trough_idx)
        episodes.append({
            "peak_date": peak_date,
            "trough_date": trough_date,
            "recovery_date": "진행중 (Active)",
            "depth_pct": round(dd_pct, 2),
            "drawdown_trades": dd_trades,
            "recovery_trades": rec_trades,
            "total_trades": max(1, len(trades) - 1 - peak_idx),
            "is_recovered": False,
        })

    recovered = [e for e in episodes if e["is_recovered"]]
    avg_rec = round(sum(e["recovery_trades"] for e in recovered) / len(recovered), 1) if recovered else 0.0
    max_rec = max((e["recovery_trades"] for e in recovered), default=0)
    avg_dd = round(sum(e["drawdown_trades"] for e in episodes) / len(episodes), 1) if episodes else 0.0

    sorted_episodes = sorted(episodes, key=lambda x: x["depth_pct"], reverse=True)
    worst_depth = sorted_episodes[0]["depth_pct"] if sorted_episodes else 0.0
    worst_trades = sorted_episodes[0]["total_trades"] if sorted_episodes else 0

    top_episodes = []
    for rank, ep in enumerate(sorted_episodes[:top_n], start=1):
        top_episodes.append({
            "rank": rank,
            **ep,
        })

    return {
        "total_episodes": len(episodes),
        "avg_recovery_trades": avg_rec,
        "max_recovery_trades": max_rec,
        "avg_drawdown_trades": avg_dd,
        "worst_dd_depth_pct": worst_depth,
        "worst_dd_trades": worst_trades,
        "current_is_recovered": (len(episodes) == 0 or episodes[-1]["is_recovered"]),
        "top_episodes": top_episodes,
    }


def calculate_rolling_window_metrics(
    trades: list[dict[str, Any]],
    window_size: int = 30,
) -> dict[str, Any]:
    """Calculate rolling window Sharpe, win rate, return, and stability metrics."""
    if not trades or len(trades) < 3:
        return {
            "rolling_window_size": window_size,
            "rolling_windows_count": 0,
            "rolling_sharpe_min": 0.0,
            "rolling_sharpe_median": 0.0,
            "rolling_sharpe_max": 0.0,
            "rolling_sharpe_std": 0.0,
            "rolling_win_rate_min_pct": 0.0,
            "rolling_win_rate_max_pct": 0.0,
            "rolling_mdd_worst_pct": 0.0,
            "pct_negative_sharpe_windows": 0.0,
            "consistency_score_pct": 0.0,
        }

    actual_window = min(window_size, len(trades))
    profits = [
        _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
        for t in trades
    ]

    sharpes = []
    win_rates = []
    returns = []
    mdds = []

    for i in range(len(profits) - actual_window + 1):
        win_slice = profits[i : i + actual_window]
        n_w = len(win_slice)
        wins = sum(1 for p in win_slice if p > 1e-6)
        wr = (wins / n_w) * 100.0
        tot_ret = sum(win_slice) * 100.0

        mean_p = sum(win_slice) / n_w if n_w > 0 else 0.0
        if n_w > 1:
            var_p = sum((x - mean_p) ** 2 for x in win_slice) / (n_w - 1)
            std_p = math.sqrt(var_p) if var_p > 0 else 0.0
        else:
            std_p = 0.0

        if std_p > 1e-9:
            sh = mean_p / std_p
        else:
            sh = 999.0 if mean_p > 0 else (-999.0 if mean_p < 0 else 0.0)

        eq = [1.0]
        for p in win_slice:
            eq.append(eq[-1] * (1.0 + p))
        peak = eq[0]
        max_dd = 0.0
        for v in eq:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        sharpes.append(sh)
        win_rates.append(wr)
        returns.append(tot_ret)
        mdds.append(max_dd * 100.0)

    num_windows = len(sharpes)
    finite_sharpes = [s for s in sharpes if math.isfinite(s) and abs(s) < 900.0]
    neg_sharpes = sum(1 for s in sharpes if s < 0.0)
    pos_returns = sum(1 for r in returns if r > 0.0)

    sh_min = round(float(min(finite_sharpes)), 2) if finite_sharpes else 0.0
    sh_med = round(_percentile(finite_sharpes, 50.0), 2) if finite_sharpes else 0.0
    sh_max = round(float(max(finite_sharpes)), 2) if finite_sharpes else 0.0
    if len(finite_sharpes) > 1:
        mean_sh = sum(finite_sharpes) / len(finite_sharpes)
        var_sh = sum((s - mean_sh) ** 2 for s in finite_sharpes) / (len(finite_sharpes) - 1)
        sh_std = round(math.sqrt(var_sh), 2) if var_sh > 0 else 0.0
    else:
        sh_std = 0.0

    wr_min = round(float(min(win_rates)), 1) if win_rates else 0.0
    wr_max = round(float(max(win_rates)), 1) if win_rates else 0.0
    mdd_worst = round(float(max(mdds)), 2) if mdds else 0.0

    pct_neg_sh = round((neg_sharpes / num_windows) * 100.0, 1) if num_windows > 0 else 0.0
    consistency = round((pos_returns / num_windows) * 100.0, 1) if num_windows > 0 else 0.0

    return {
        "rolling_window_size": actual_window,
        "rolling_windows_count": num_windows,
        "rolling_sharpe_min": sh_min,
        "rolling_sharpe_median": sh_med,
        "rolling_sharpe_max": sh_max,
        "rolling_sharpe_std": sh_std,
        "rolling_win_rate_min_pct": wr_min,
        "rolling_win_rate_max_pct": wr_max,
        "rolling_mdd_worst_pct": mdd_worst,
        "pct_negative_sharpe_windows": pct_neg_sh,
        "consistency_score_pct": consistency,
    }


def calculate_stake_amount_tier_breakdown(
    trades: list[dict[str, Any]],
    sort_by: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Segment trade performance by position stake amount (capital size) tiers.

    Extracts stake amount per trade using keys: 'stake_amount', 'cost', 'stake',
    'position_size', or ('open_rate' * 'amount').
    Groups trades into size categories (e.g., Micro, Low, Mid, Large) based on
    quantiles or distinct values.

    Computes win rate, total profit %, average profit %, total stake volume,
    profit factor, win/loss ratio, trade expectancy in bps, max win %, max loss %,
    and share of total volume (%).
    """
    if not trades:
        return {}

    def _extract_stake(t: dict[str, Any]) -> float:
        for k in ("stake_amount", "cost", "stake", "position_size"):
            if k in t and t[k] is not None:
                val = _safe_float(t[k], -1.0)
                if val > 0:
                    return val
        open_r = _safe_float(t.get("open_rate", 0.0))
        amt = _safe_float(t.get("amount", 0.0))
        if open_r > 0 and amt > 0:
            return open_r * amt
        return 0.0

    parsed_trades: list[tuple[float, dict[str, Any]]] = []
    for t in trades:
        s = _extract_stake(t)
        if s > 0:
            parsed_trades.append((s, t))

    if not parsed_trades:
        return {}

    stakes = [item[0] for item in parsed_trades]
    grand_total_stake = sum(stakes)
    unique_stakes = sorted(list(set(stakes)))

    groups: dict[str, list[tuple[float, dict[str, Any]]]] = {}

    if len(unique_stakes) == 1:
        tier_label = f"Fixed (${unique_stakes[0]:g})"
        groups[tier_label] = parsed_trades
    elif len(unique_stakes) <= 3:
        for s_val in unique_stakes:
            lbl = f"Tier (${s_val:g})"
            groups[lbl] = [item for item in parsed_trades if item[0] == s_val]
    else:
        q25 = _percentile(stakes, 25.0)
        q50 = _percentile(stakes, 50.0)
        q75 = _percentile(stakes, 75.0)

        raw_cutoffs = sorted(list(set([min(stakes), q25, q50, q75, max(stakes)])))
        if len(raw_cutoffs) == 5:
            tier_names = [
                f"Tier 1 Micro (<= ${q25:g})",
                f"Tier 2 Low (${q25:g} - ${q50:g})",
                f"Tier 3 Mid (${q50:g} - ${q75:g})",
                f"Tier 4 Large (> ${q75:g})",
            ]
            for name in tier_names:
                groups[name] = []
            for s, t in parsed_trades:
                if s <= q25:
                    groups[tier_names[0]].append((s, t))
                elif s <= q50:
                    groups[tier_names[1]].append((s, t))
                elif s <= q75:
                    groups[tier_names[2]].append((s, t))
                else:
                    groups[tier_names[3]].append((s, t))
        else:
            for i in range(len(raw_cutoffs) - 1):
                low, high = raw_cutoffs[i], raw_cutoffs[i + 1]
                if i == 0:
                    lbl = f"Tier {i+1} (<= ${high:g})"
                    bin_trades = [item for item in parsed_trades if item[0] <= high]
                elif i == len(raw_cutoffs) - 2:
                    lbl = f"Tier {i+1} (> ${low:g})"
                    bin_trades = [item for item in parsed_trades if item[0] > low]
                else:
                    lbl = f"Tier {i+1} (${low:g} - ${high:g})"
                    bin_trades = [item for item in parsed_trades if low < item[0] <= high]
                groups[lbl] = bin_trades

    breakdown: dict[str, dict[str, Any]] = {}
    for tier_label, item_list in groups.items():
        count = len(item_list)
        if count == 0:
            continue

        wins: list[float] = []
        losses: list[float] = []
        profits: list[float] = []
        tier_stakes = [item[0] for item in item_list]

        for s, t in item_list:
            p = _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
            profits.append(p)
            if p > 1e-6:
                wins.append(p * 100.0)
            elif p < -1e-6:
                losses.append(abs(p * 100.0))

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / count) * 100.0 if count > 0 else 0.0
        total_profit_pct = sum(profits) * 100.0
        avg_profit_pct = (total_profit_pct / count) if count > 0 else 0.0
        tot_stake = sum(tier_stakes)
        avg_stake = tot_stake / count if count > 0 else 0.0
        pf = (sum(wins) / sum(losses)) if sum(losses) > 0 else (999.0 if sum(wins) > 0 else 0.0)
        avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
        avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
        p_win = win_count / count if count > 0 else 0.0
        p_loss = loss_count / count if count > 0 else 0.0
        exp_pct = (p_win * avg_win) - (p_loss * avg_loss)
        wl_ratio = (avg_win / avg_loss) if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)
        vol_share = (tot_stake / grand_total_stake) * 100.0 if grand_total_stake > 0 else 0.0

        breakdown[tier_label] = {
            "trades": count,
            "wins": win_count,
            "losses": loss_count,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_pct": round(total_profit_pct, 2),
            "avg_profit_pct": round(avg_profit_pct, 2),
            "total_stake": round(tot_stake, 2),
            "avg_stake": round(avg_stake, 2),
            "min_stake": round(min(tier_stakes), 2) if tier_stakes else 0.0,
            "max_stake": round(max(tier_stakes), 2) if tier_stakes else 0.0,
            "profit_factor": round(pf, 2),
            "win_loss_ratio": round(wl_ratio, 2),
            "expectancy_bps": round(exp_pct * 100.0, 1),
            "max_win_pct": round(max(wins), 2) if wins else 0.0,
            "max_loss_pct": round(max(losses), 2) if losses else 0.0,
            "volume_share_pct": round(vol_share, 1),
        }

    sort_map = {
        "trades": "trades",
        "profit": "total_profit_pct",
        "total_profit_pct": "total_profit_pct",
        "win_rate": "win_rate_pct",
        "win_rate_pct": "win_rate_pct",
        "pf": "profit_factor",
        "profit_factor": "profit_factor",
        "stake": "total_stake",
        "total_stake": "total_stake",
    }
    actual_sort = sort_map.get(sort_by, sort_by) if sort_by else None
    if actual_sort and breakdown:
        breakdown = dict(sorted(breakdown.items(), key=lambda item: item[1].get(actual_sort, 0), reverse=True))

    return breakdown


def simulate_slippage_fee_sensitivity(
    trades: list[dict[str, Any]],
    friction_steps_bps: list[float] | None = None,
) -> dict[str, Any]:
    """Stress test strategy performance across incremental slippage and execution fee levels.

    Simulates performance degradation under realistic live exchange friction
    (taker fees, spread crossing, order book slippage, execution latency).

    Evaluates incremental friction steps (default: 0, 5, 10, 15, 20, 25, 30, 40, 50 bps per trade).
    Calculates:
    - breakeven_friction_bps: maximum per-trade cost in bps before strategy expectation drops to zero
    - sensitivity_curve: list of metric dictionaries for each friction step
    - resilience_rating: 'High Resilience', 'Moderate Resilience', 'Low Resilience', or 'Fragile'.
    """
    if not trades:
        return {
            "breakeven_friction_bps": 0.0,
            "resilience_rating": "N/A",
            "sensitivity_curve": [],
        }

    profits = [
        _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
        for t in trades
    ]
    if not profits:
        return {
            "breakeven_friction_bps": 0.0,
            "resilience_rating": "N/A",
            "sensitivity_curve": [],
        }

    n = len(profits)
    mean_p = sum(profits) / n if n > 0 else 0.0
    breakeven_bps = max(0.0, round(mean_p * 10000.0, 1))

    if breakeven_bps >= 35.0:
        rating = "High Resilience (Institutional Grade)"
    elif breakeven_bps >= 15.0:
        rating = "Moderate Resilience (Standard)"
    elif breakeven_bps >= 5.0:
        rating = "Low Resilience (Friction Sensitive)"
    else:
        rating = "Fragile (Unviable Live Friction)"

    if friction_steps_bps is None:
        steps = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0]
    else:
        steps = sorted(friction_steps_bps)

    base_tot_ret = sum(profits) * 100.0
    curve: list[dict[str, Any]] = []

    for step in steps:
        friction_dec = step / 10000.0
        adj_p = [p - friction_dec for p in profits]

        wins = [p for p in adj_p if p > 1e-6]
        losses = [abs(p) for p in adj_p if p < -1e-6]

        wr = (len(wins) / n) * 100.0 if n > 0 else 0.0
        tot_ret = sum(adj_p) * 100.0
        exp_bps = (sum(adj_p) / n) * 10000.0 if n > 0 else 0.0
        pf = (sum(wins) / sum(losses)) if sum(losses) > 0 else (999.0 if sum(wins) > 0 else 0.0)

        if abs(base_tot_ret) > 1e-6:
            decay_pct = ((base_tot_ret - tot_ret) / abs(base_tot_ret)) * 100.0
        else:
            decay_pct = 0.0

        curve.append({
            "friction_bps": float(step),
            "win_rate_pct": round(wr, 2),
            "total_return_pct": round(tot_ret, 2),
            "profit_factor": round(pf, 2),
            "expectancy_bps": round(exp_bps, 1),
            "return_decay_pct": round(decay_pct, 1),
        })

    return {
        "breakeven_friction_bps": breakeven_bps,
        "resilience_rating": rating,
        "sensitivity_curve": curve,
    }


def calculate_trade_profit_concentration(
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Analyze trade profit concentration, Herfindahl index (HHI), Gini inequality, and outlier overfitting.

    Evaluates whether strategy alpha is robustly and organically distributed across many trades
    or deceptively driven by a few lucky outlier mega-winners.
    """
    if not trades:
        return {
            "top_1_profit_share_pct": 0.0,
            "top_3_profit_share_pct": 0.0,
            "top_5_profit_share_pct": 0.0,
            "top_10pct_profit_share_pct": 0.0,
            "herfindahl_index": 0.0,
            "gini_coefficient": 0.0,
            "profit_without_top_1_pct": 0.0,
            "profit_without_top_3_pct": 0.0,
            "pf_without_top_3": 0.0,
            "is_profitable_without_top_3": False,
            "trimmed_profit_decay_pct": 0.0,
            "robustness_rating": "N/A",
        }

    profits = [
        _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
        for t in trades
    ]
    if not profits:
        return {
            "top_1_profit_share_pct": 0.0,
            "top_3_profit_share_pct": 0.0,
            "top_5_profit_share_pct": 0.0,
            "top_10pct_profit_share_pct": 0.0,
            "herfindahl_index": 0.0,
            "gini_coefficient": 0.0,
            "profit_without_top_1_pct": 0.0,
            "profit_without_top_3_pct": 0.0,
            "pf_without_top_3": 0.0,
            "is_profitable_without_top_3": False,
            "trimmed_profit_decay_pct": 0.0,
            "robustness_rating": "N/A",
        }

    total_net_return = sum(profits) * 100.0
    winning_profits = sorted([p for p in profits if p > 1e-6], reverse=True)
    losing_profits = [abs(p) for p in profits if p < -1e-6]
    total_win_profit = sum(winning_profits)

    if total_win_profit > 1e-9:
        top_1_share = (winning_profits[0] / total_win_profit) * 100.0
        top_3_share = (sum(winning_profits[:3]) / total_win_profit) * 100.0
        top_5_share = (sum(winning_profits[:5]) / total_win_profit) * 100.0
        k_10pct = max(1, math.ceil(len(winning_profits) * 0.10))
        top_10pct_share = (sum(winning_profits[:k_10pct]) / total_win_profit) * 100.0
        hhi = sum(((p / total_win_profit) ** 2) for p in winning_profits) * 10000.0

        # Gini coefficient of winning trades (0.0 = uniform, 1.0 = single trade)
        m = len(winning_profits)
        if m > 1:
            sorted_asc = sorted(winning_profits)
            cum_rank_sum = sum((i + 1) * w for i, w in enumerate(sorted_asc))
            gini = (2.0 * cum_rank_sum) / (m * total_win_profit) - ((m + 1.0) / m)
            gini = max(0.0, min(1.0, gini))
        else:
            gini = 1.0 if m == 1 else 0.0
    else:
        top_1_share = 0.0
        top_3_share = 0.0
        top_5_share = 0.0
        top_10pct_share = 0.0
        hhi = 0.0
        gini = 0.0

    sorted_desc = sorted(profits, reverse=True)
    without_top_1 = sorted_desc[1:] if len(sorted_desc) > 1 else []
    without_top_3 = sorted_desc[3:] if len(sorted_desc) > 3 else []

    profit_no_top_1 = sum(without_top_1) * 100.0
    profit_no_top_3 = sum(without_top_3) * 100.0
    wins_no_top_3 = sum(p for p in without_top_3 if p > 1e-6)
    loss_no_top_3 = sum(abs(p) for p in without_top_3 if p < -1e-6)
    pf_no_top_3 = (wins_no_top_3 / loss_no_top_3) if loss_no_top_3 > 0 else (999.0 if wins_no_top_3 > 0 else 0.0)
    is_profitable_no_top_3 = profit_no_top_3 > 0.0

    if total_net_return > 1e-6:
        decay_pct = max(0.0, ((total_net_return - profit_no_top_3) / total_net_return) * 100.0)
    else:
        decay_pct = 100.0 if profit_no_top_3 <= 0 else 0.0

    if total_win_profit <= 1e-6 or total_net_return <= 0.0:
        rating = "Unprofitable (No Positive Edge)"
    elif not is_profitable_no_top_3:
        rating = "Severe Outlier Overfitting (Fragile)"
    elif top_3_share > 60.0 or pf_no_top_3 < 1.10 or hhi > 2500.0:
        rating = "High Concentration Risk (Outlier Dependent)"
    elif top_3_share > 35.0 or pf_no_top_3 < 1.25:
        rating = "Moderate Concentration (Acceptable)"
    else:
        rating = "Robust Distribution (Institutional Grade)"

    return {
        "top_1_profit_share_pct": round(top_1_share, 2),
        "top_3_profit_share_pct": round(top_3_share, 2),
        "top_5_profit_share_pct": round(top_5_share, 2),
        "top_10pct_profit_share_pct": round(top_10pct_share, 2),
        "herfindahl_index": round(hhi, 1),
        "gini_coefficient": round(gini, 3),
        "profit_without_top_1_pct": round(profit_no_top_1, 2),
        "profit_without_top_3_pct": round(profit_no_top_3, 2),
        "pf_without_top_3": round(pf_no_top_3, 2),
        "is_profitable_without_top_3": is_profitable_no_top_3,
        "trimmed_profit_decay_pct": round(decay_pct, 1),
        "robustness_rating": rating,
    }


def _extract_trade_open_close_seconds(trade: dict[str, Any]) -> tuple[float | None, float | None]:
    """Helper to safely extract open and close timestamps in epoch seconds."""
    open_ts: float | None = None
    close_ts: float | None = None

    for key in ("open_timestamp", "open_date"):
        val = trade.get(key)
        if isinstance(val, (int, float)) and val > 0:
            open_ts = val / 1000.0 if val > 1e11 else float(val)
            break
        elif isinstance(val, str) and val.strip():
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                open_ts = dt.timestamp()
                break
            except Exception:
                pass

    for key in ("close_timestamp", "close_date"):
        val = trade.get(key)
        if isinstance(val, (int, float)) and val > 0:
            close_ts = val / 1000.0 if val > 1e11 else float(val)
            break
        elif isinstance(val, str) and val.strip():
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                close_ts = dt.timestamp()
                break
            except Exception:
                pass

    if close_ts is None and open_ts is not None:
        dur = _safe_float(trade.get("trade_duration", trade.get("duration", 0.0)))
        if dur > 0:
            close_ts = open_ts + dur * 60.0
        else:
            close_ts = open_ts

    if open_ts is not None and close_ts is not None and close_ts < open_ts:
        close_ts = open_ts
    return open_ts, close_ts


def calculate_concurrency_exposure_analysis(
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Analyze concurrent open position overlaps, capital utilization, and slot density performance.

    Evaluates:
    - peak_concurrent_trades: Maximum number of trades open simultaneously
    - avg_concurrent_trades: Time-weighted average number of concurrent trades
    - idle_time_pct: % of backtest duration with 0 active positions (idle cash drag)
    - active_time_pct: % of backtest duration with at least 1 active position
    - concurrency_distribution: % of time spent at each concurrency level
    - slot_tier_performance: Win rate, profit, and expectancy by concurrent slot density at entry
    - correlation_overload_penalty_pct: Drop in win rate when entering with >=3 concurrent trades vs solo
    - capital_efficiency_rating: Institutional utilization rating
    """
    if not trades:
        return {
            "peak_concurrent_trades": 0,
            "avg_concurrent_trades": 0.0,
            "idle_time_pct": 0.0,
            "active_time_pct": 0.0,
            "concurrency_distribution": {},
            "slot_tier_performance": {},
            "correlation_overload_penalty_pct": 0.0,
            "capital_efficiency_rating": "N/A",
        }

    valid_intervals: list[tuple[int, float, float, float]] = []  # (trade_idx, open_ts, close_ts, profit)
    for idx, t in enumerate(trades):
        o_ts, c_ts = _extract_trade_open_close_seconds(t)
        if o_ts is not None and c_ts is not None:
            p = _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
            valid_intervals.append((idx, o_ts, c_ts, p))

    if not valid_intervals:
        return {
            "peak_concurrent_trades": 0,
            "avg_concurrent_trades": 0.0,
            "idle_time_pct": 0.0,
            "active_time_pct": 0.0,
            "concurrency_distribution": {},
            "slot_tier_performance": {},
            "correlation_overload_penalty_pct": 0.0,
            "capital_efficiency_rating": "N/A",
        }

    # 1. Timeline event sweep line for duration and time-weighted concurrency
    events: list[tuple[float, int]] = []
    min_time = min(item[1] for item in valid_intervals)
    max_time = max(item[2] for item in valid_intervals)
    total_duration_s = max_time - min_time

    for _, o_ts, c_ts, _ in valid_intervals:
        events.append((o_ts, 1))
        events.append((c_ts, -1))

    # Sort events: if same timestamp, process closes (-1) before opens (+1)
    events.sort(key=lambda x: (x[0], x[1]))

    time_at_count: dict[int, float] = {}
    curr_concurrent = 0
    curr_time = events[0][0] if events else 0.0
    peak_concurrent = 0

    for ev_time, ev_delta in events:
        dt = ev_time - curr_time
        if dt > 0:
            time_at_count[curr_concurrent] = time_at_count.get(curr_concurrent, 0.0) + dt
        curr_time = ev_time
        curr_concurrent += ev_delta
        if curr_concurrent > peak_concurrent:
            peak_concurrent = curr_concurrent

    if total_duration_s > 0:
        idle_s = time_at_count.get(0, 0.0)
        idle_pct = (idle_s / total_duration_s) * 100.0
        active_pct = 100.0 - idle_pct
        avg_concurrent = sum(cnt * dur for cnt, dur in time_at_count.items()) / total_duration_s
        concurrency_dist = {
            f"{cnt} Trades": round((dur / total_duration_s) * 100.0, 1)
            for cnt, dur in sorted(time_at_count.items())
        }
    else:
        idle_pct = 0.0
        active_pct = 100.0
        avg_concurrent = float(len(valid_intervals))
        concurrency_dist = {f"{len(valid_intervals)} Trades": 100.0}

    # 2. Concurrency at entry for each trade
    SLOT_BUCKETS = [
        ("Solo (1 Slot)", 1, 1),
        ("Dual (2 Slots)", 2, 2),
        ("Moderate (3-4 Slots)", 3, 4),
        ("Heavy (5+ Slots)", 5, 9999),
    ]

    bucket_trades: dict[str, list[float]] = {name: [] for name, _, _ in SLOT_BUCKETS}

    for idx, o_ts, c_ts, p in valid_intervals:
        # Count overlapping active trades at entry time o_ts
        slot_density = 1 + sum(
            1 for o_idx, other_o, other_c, _ in valid_intervals
            if o_idx != idx and other_o <= o_ts < other_c
        )
        for b_name, b_min, b_max in SLOT_BUCKETS:
            if b_min <= slot_density <= b_max:
                bucket_trades[b_name].append(p)
                break

    slot_perf: dict[str, dict[str, Any]] = {}
    for b_name, _, _ in SLOT_BUCKETS:
        p_list = bucket_trades[b_name]
        cnt = len(p_list)
        if cnt == 0:
            continue
        wins = [x * 100.0 for x in p_list if x > 1e-6]
        losses = [abs(x * 100.0) for x in p_list if x < -1e-6]
        wr = (len(wins) / cnt) * 100.0
        tot_ret = sum(p_list) * 100.0
        exp_bps = (sum(p_list) / cnt) * 10000.0
        pf = (sum(wins) / sum(losses)) if sum(losses) > 0 else (999.0 if sum(wins) > 0 else 0.0)

        slot_perf[b_name] = {
            "trades": cnt,
            "win_rate_pct": round(wr, 2),
            "total_profit_pct": round(tot_ret, 2),
            "profit_factor": round(pf, 2),
            "expectancy_bps": round(exp_bps, 1),
        }

    # 3. Overload penalty and rating
    solo_wr = slot_perf.get("Solo (1 Slot)", {}).get("win_rate_pct", 0.0)
    heavy_wr = slot_perf.get("Moderate (3-4 Slots)", {}).get(
        "win_rate_pct",
        slot_perf.get("Heavy (5+ Slots)", {}).get("win_rate_pct", solo_wr)
    )
    overload_penalty = max(0.0, round(solo_wr - heavy_wr, 1))

    if avg_concurrent >= 2.0 and idle_pct < 35.0:
        eff_rating = "High Capital Efficiency (Active Deployment)"
    elif idle_pct > 65.0:
        eff_rating = "Underutilized Capital (High Idle Drag)"
    elif peak_concurrent >= 5 and overload_penalty >= 15.0:
        eff_rating = "High Congestion Risk (Correlated Stopouts)"
    else:
        eff_rating = "Balanced Exposure (Controlled Risk)"

    return {
        "peak_concurrent_trades": peak_concurrent,
        "avg_concurrent_trades": round(avg_concurrent, 2),
        "idle_time_pct": round(idle_pct, 1),
        "active_time_pct": round(active_pct, 1),
        "concurrency_distribution": concurrency_dist,
        "slot_tier_performance": slot_perf,
        "correlation_overload_penalty_pct": overload_penalty,
        "capital_efficiency_rating": eff_rating,
    }


def calculate_mae_mfe_edge_analysis(
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Analyze Maximum Adverse Excursion (MAE), Maximum Favorable Excursion (MFE),
    edge ratios, exit capture efficiency, and stop-loss placement calibration.

    Evaluates:
    - avg_mae_pct: Average intra-trade drawdown experienced across all trades
    - avg_mfe_pct: Average intra-trade peak potential profit across all trades
    - avg_win_mae_pct: Intra-trade drawdown tolerated on winning trades (pain before gain)
    - avg_win_mfe_pct: Peak potential run-up achieved on winning trades
    - avg_win_capture_pct: Exit capture efficiency (realized win return / peak MFE)
    - avg_loss_mae_pct: Maximum drawdown suffered on losing trades
    - avg_loss_mfe_pct: Potential profit reached on losing trades prior to exit (surrendered profit)
    - wasted_winners_count: Number of losing trades that reached >= +1.0% MFE before closing red
    - wasted_winners_pct: Percentage of losing trades that were wasted winners
    - edge_ratio: Ratio of favorable excursion to adverse excursion (MFE / |MAE|)
    - optimal_sl_suggestion_pct: 95th percentile MAE of winning trades + 15% buffer
    - edge_rating: Qualitative execution and statistical edge rating
    - capture_distribution: Win trades categorized by capture efficiency tiers
    """
    if not trades:
        return {
            "avg_mae_pct": 0.0,
            "avg_mfe_pct": 0.0,
            "avg_win_mae_pct": 0.0,
            "avg_win_mfe_pct": 0.0,
            "avg_win_capture_pct": 0.0,
            "avg_loss_mae_pct": 0.0,
            "avg_loss_mfe_pct": 0.0,
            "wasted_winners_count": 0,
            "wasted_winners_pct": 0.0,
            "edge_ratio": 0.0,
            "optimal_sl_suggestion_pct": 0.0,
            "edge_rating": "N/A",
            "capture_distribution": {},
        }

    records: list[dict[str, float]] = []

    for t in trades:
        is_short = bool(t.get("is_short", False) or t.get("trade_direction") == "short")
        o_rate = _safe_float(t.get("open_rate", t.get("open_price", 0.0)))
        c_rate = _safe_float(t.get("close_rate", t.get("close_price", 0.0)))
        p_ratio = _safe_float(t.get("profit_ratio", t.get("profit_pct", 0.0) / 100.0 if "profit_pct" in t else 0.0))
        realized_pct = p_ratio * 100.0

        min_rate = t.get("min_rate", t.get("min_price"))
        max_rate = t.get("max_rate", t.get("max_price"))

        if o_rate > 0:
            p_min = _safe_float(min_rate) if min_rate is not None else (min(o_rate, c_rate) if c_rate > 0 else o_rate)
            p_max = _safe_float(max_rate) if max_rate is not None else (max(o_rate, c_rate) if c_rate > 0 else o_rate)

            if not is_short:
                raw_mae = ((p_min - o_rate) / o_rate) * 100.0
                raw_mfe = ((p_max - o_rate) / o_rate) * 100.0
            else:
                raw_mae = ((o_rate - p_max) / o_rate) * 100.0
                raw_mfe = ((o_rate - p_min) / o_rate) * 100.0
        else:
            if realized_pct >= 0:
                raw_mfe = realized_pct
                raw_mae = 0.0
            else:
                raw_mfe = 0.0
                raw_mae = realized_pct

        mae_pct = min(0.0, raw_mae)
        mfe_pct = max(0.0, raw_mfe)

        if mfe_pct > 1e-4 and realized_pct > 0:
            cap_ratio = min(100.0, max(0.0, (realized_pct / mfe_pct) * 100.0))
        elif realized_pct <= 0:
            cap_ratio = 0.0
        else:
            cap_ratio = 100.0

        records.append({
            "profit_ratio": p_ratio,
            "realized_pct": realized_pct,
            "mae_pct": mae_pct,
            "mfe_pct": mfe_pct,
            "capture_pct": cap_ratio,
        })

    n = len(records)
    wins = [r for r in records if r["profit_ratio"] > 1e-6]
    losses = [r for r in records if r["profit_ratio"] < -1e-6]

    avg_mae = sum(r["mae_pct"] for r in records) / n
    avg_mfe = sum(r["mfe_pct"] for r in records) / n

    avg_win_mae = (sum(r["mae_pct"] for r in wins) / len(wins)) if wins else 0.0
    avg_win_mfe = (sum(r["mfe_pct"] for r in wins) / len(wins)) if wins else 0.0
    avg_win_cap = (sum(r["capture_pct"] for r in wins) / len(wins)) if wins else 0.0

    avg_loss_mae = (sum(r["mae_pct"] for r in losses) / len(losses)) if losses else 0.0
    avg_loss_mfe = (sum(r["mfe_pct"] for r in losses) / len(losses)) if losses else 0.0

    wasted_count = sum(1 for r in losses if r["mfe_pct"] >= 1.0)
    wasted_pct = (wasted_count / len(losses) * 100.0) if losses else 0.0

    abs_mae = abs(avg_mae)
    if abs_mae > 1e-6:
        edge_ratio = avg_mfe / abs_mae
    else:
        edge_ratio = 999.0 if avg_mfe > 0 else 1.0

    win_maes = [abs(r["mae_pct"]) for r in wins]
    if win_maes:
        win_maes.sort()
        idx = int(0.95 * len(win_maes))
        idx = min(idx, len(win_maes) - 1)
        p95 = win_maes[idx]
        optimal_sl = round(p95 * 1.15, 2)
    else:
        optimal_sl = 0.0

    if edge_ratio >= 1.6 and avg_win_cap >= 50.0:
        rating = "High Edge & Optimal Exit Execution"
    elif edge_ratio >= 1.2 and avg_win_cap >= 35.0:
        rating = "Solid Statistical Edge (Healthy Execution)"
    elif edge_ratio >= 1.0:
        rating = "Marginal Edge (High Underwater Drag)"
    else:
        rating = "Suboptimal Edge (Negative Excursion Drag)"

    cap_tiers = {
        "Peak Capture (>=70%)": 0,
        "Good Capture (40-70%)": 0,
        "Suboptimal Capture (<40%)": 0,
    }
    for w in wins:
        c = w["capture_pct"]
        if c >= 70.0:
            cap_tiers["Peak Capture (>=70%)"] += 1
        elif c >= 40.0:
            cap_tiers["Good Capture (40-70%)"] += 1
        else:
            cap_tiers["Suboptimal Capture (<40%)"] += 1

    return {
        "avg_mae_pct": round(avg_mae, 2),
        "avg_mfe_pct": round(avg_mfe, 2),
        "avg_win_mae_pct": round(avg_win_mae, 2),
        "avg_win_mfe_pct": round(avg_win_mfe, 2),
        "avg_win_capture_pct": round(avg_win_cap, 1),
        "avg_loss_mae_pct": round(avg_loss_mae, 2),
        "avg_loss_mfe_pct": round(avg_loss_mfe, 2),
        "wasted_winners_count": wasted_count,
        "wasted_winners_pct": round(wasted_pct, 1),
        "edge_ratio": round(edge_ratio, 2),
        "optimal_sl_suggestion_pct": optimal_sl,
        "edge_rating": rating,
        "capture_distribution": cap_tiers,
    }


def parse_freqtrade_backtest_json(
    json_data: dict[str, Any],
    sort_by: str | None = None,
    min_trades: int = 1,
    monte_carlo: bool = False,
    mc_iterations: int = 1000,
    mc_threshold_pct: float = 20.0,
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
        ann_metrics = calculate_annualized_metrics(
            trades=trades,
            total_return_pct=dd_metrics["total_return_pct"],
            max_drawdown_pct=dd_metrics["max_drawdown_pct"],
            backtest_days=strat_data.get("backtest_days"),
            backtest_start_ts=strat_data.get("backtest_start_ts"),
            backtest_end_ts=strat_data.get("backtest_end_ts"),
        )
        mc_metrics = {}
        if monte_carlo:
            mc_metrics = simulate_monte_carlo_drawdown(
                trades=trades,
                iterations=mc_iterations,
                threshold_mdd_pct=mc_threshold_pct,
            )
        exit_breakdown = calculate_exit_reason_breakdown(trades, sort_by=sort_by, min_trades=min_trades)
        pair_breakdown = calculate_pair_performance_breakdown(trades, sort_by=sort_by, min_trades=min_trades)
        dir_breakdown = calculate_direction_breakdown(trades)
        dow_breakdown = calculate_day_of_week_breakdown(trades, sort_by=sort_by)
        hourly_breakdown = calculate_hourly_breakdown(trades, sort_by=sort_by)
        duration_breakdown = calculate_duration_tier_breakdown(trades, sort_by=sort_by)
        stake_tier_breakdown = calculate_stake_amount_tier_breakdown(trades, sort_by=sort_by)
        monthly_breakdown = calculate_monthly_breakdown(trades, sort_by=sort_by)
        dd_episodes = calculate_drawdown_episodes(trades)
        rolling_metrics = calculate_rolling_window_metrics(trades, window_size=30)
        slippage_sensitivity = simulate_slippage_fee_sensitivity(trades)
        profit_concentration = calculate_trade_profit_concentration(trades)
        concurrency_analysis = calculate_concurrency_exposure_analysis(trades)
        mae_mfe_analysis = calculate_mae_mfe_edge_analysis(trades)

        combined = {
            "strategy": strat_name,
            **trade_metrics,
            **dd_metrics,
            **ann_metrics,
            **mc_metrics,
            **rolling_metrics,
            "drawdown_episodes": dd_episodes,
            "avg_recovery_trades": dd_episodes["avg_recovery_trades"],
            "max_recovery_trades": dd_episodes["max_recovery_trades"],
            "total_drawdown_episodes": dd_episodes["total_episodes"],
            "worst_dd_depth_pct": dd_episodes["worst_dd_depth_pct"],
            "worst_dd_trades": dd_episodes["worst_dd_trades"],
            "exit_reasons": exit_breakdown,
            "pair_performance": pair_breakdown,
            "direction_performance": dir_breakdown,
            "day_of_week_performance": dow_breakdown,
            "hourly_performance": hourly_breakdown,
            "duration_tier_performance": duration_breakdown,
            "stake_tier_performance": stake_tier_breakdown,
            "monthly_performance": monthly_breakdown,
            "slippage_sensitivity": slippage_sensitivity,
            "breakeven_friction_bps": slippage_sensitivity["breakeven_friction_bps"],
            "slippage_resilience_rating": slippage_sensitivity["resilience_rating"],
            "profit_concentration": profit_concentration,
            "top_1_profit_share_pct": profit_concentration["top_1_profit_share_pct"],
            "top_3_profit_share_pct": profit_concentration["top_3_profit_share_pct"],
            "top_5_profit_share_pct": profit_concentration["top_5_profit_share_pct"],
            "top_10pct_profit_share_pct": profit_concentration["top_10pct_profit_share_pct"],
            "herfindahl_index": profit_concentration["herfindahl_index"],
            "gini_coefficient": profit_concentration["gini_coefficient"],
            "profit_without_top_1_pct": profit_concentration["profit_without_top_1_pct"],
            "profit_without_top_3_pct": profit_concentration["profit_without_top_3_pct"],
            "pf_without_top_3": profit_concentration["pf_without_top_3"],
            "is_profitable_without_top_3": profit_concentration["is_profitable_without_top_3"],
            "trimmed_profit_decay_pct": profit_concentration["trimmed_profit_decay_pct"],
            "concentration_robustness_rating": profit_concentration["robustness_rating"],
            "concurrency_analysis": concurrency_analysis,
            "peak_concurrent_trades": concurrency_analysis["peak_concurrent_trades"],
            "avg_concurrent_trades": concurrency_analysis["avg_concurrent_trades"],
            "idle_time_pct": concurrency_analysis["idle_time_pct"],
            "capital_efficiency_rating": concurrency_analysis["capital_efficiency_rating"],
            "correlation_overload_penalty_pct": concurrency_analysis["correlation_overload_penalty_pct"],
            "mae_mfe_analysis": mae_mfe_analysis,
            "avg_mae_pct": mae_mfe_analysis["avg_mae_pct"],
            "avg_mfe_pct": mae_mfe_analysis["avg_mfe_pct"],
            "avg_win_mae_pct": mae_mfe_analysis["avg_win_mae_pct"],
            "avg_win_mfe_pct": mae_mfe_analysis["avg_win_mfe_pct"],
            "avg_win_capture_pct": mae_mfe_analysis["avg_win_capture_pct"],
            "avg_loss_mae_pct": mae_mfe_analysis["avg_loss_mae_pct"],
            "avg_loss_mfe_pct": mae_mfe_analysis["avg_loss_mfe_pct"],
            "wasted_winners_count": mae_mfe_analysis["wasted_winners_count"],
            "wasted_winners_pct": mae_mfe_analysis["wasted_winners_pct"],
            "edge_ratio": mae_mfe_analysis["edge_ratio"],
            "optimal_sl_suggestion_pct": mae_mfe_analysis["optimal_sl_suggestion_pct"],
            "edge_rating": mae_mfe_analysis["edge_rating"],
        }
        strategy_results[strat_name] = combined

    return strategy_results


def generate_markdown_report(analysis_results: dict[str, Any]) -> str:
    """Generate Markdown report for backtest quantitative analysis."""
    lines = [
        "# 📊 Freqtrade 전략 심층 퀀트 리스크 및 하방 위험 분석 보고서",
        "",
        "| 전략명 | 총 거래 | 승률 | 최대 연승/연패 | 연승/연패비 | 런 검정(Z) | 손익비(P.F.) | CPC 지수 | SQN(품질지수) | 오메가(Omega) | 왜도(Skew) | 첨도(Kurt) | 테일 비율(Tail) | 상식 비율(CSR) | 기대값(Trade Exp.) | 켈리 비율(Full/Half) | 파산 위험률(Ruin) | 최대 이익/손실 | 수익률 표준편차 | VaR(95%) | CVaR(95%) | 최대낙폭(MDD) | DaR(95%) | CDaR(95%) | CDaR 비율 | 궤양지수(Ulcer Index) | K-비율(K-Ratio) | 소르티노 비율 | 버크 비율(Burke) | 스털링 비율(Sterling) | 게인투페인(GPR) | 마틴 비율(UPI) | 칼마 비율 | RoMaD | 연환산 칼마 | 연환산 샤프 | CAGR | 기간(일) | 회복 계수 | 수중 기간(Underwater) | 최대 침체(거래) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for name, data in analysis_results.items():
        max_cw = data.get("max_consecutive_wins", 0)
        max_cl = data.get("max_consecutive_losses", 0)
        streak_str = f"{max_cw}승/{max_cl}패"
        streak_ratio_str = f"{data.get('streak_ratio', 0.0):.2f}"
        runs_z = data.get("runs_test_zscore", 0.0)
        runs_r = data.get("runs_test_rating", "N/A")
        runs_str = f"{runs_z:+.2f}" if runs_r != "N/A" else "N/A"
        cpc_str = f"{data.get('cpc_index', 0.0):.2f}"
        romad_str = f"{data.get('romad_ratio', 0.0):.2f}"
        full_k = data.get("full_kelly_pct", 0.0)
        half_k = data.get("half_kelly_pct", 0.0)
        kelly_str = f"{full_k:.1f}%/{half_k:.1f}%"
        extrema_str = f"+{data.get('max_win_pct', 0.0):.1f}%/-{data.get('max_loss_pct', 0.0):.1f}%"
        std_str = f"{data.get('std_profit_pct', 0.0):.2f}%"
        sqn_val = data.get("sqn", 0.0)
        sqn_r = data.get("sqn_rating", "N/A")
        sqn_str = f"{sqn_val:.2f} ({sqn_r})"
        lines.append(
            f"| **{name}** | {data.get('total_trades', 0)}회 | {data.get('win_rate_pct', 0.0):.1f}% | {streak_str} | {streak_ratio_str} | {runs_str} | "
            f"{data.get('profit_factor', 0.0):.2f} | {cpc_str} | {sqn_str} | "
            f"{data.get('omega_ratio', 0.0):.2f} | "
            f"{data.get('skewness', 0.0):+.2f} | {data.get('kurtosis', 0.0):+.2f} | "
            f"{data.get('tail_ratio', 0.0):.2f} | {data.get('common_sense_ratio', 0.0):.2f} | "
            f"{data.get('expectancy_pct', 0.0):+.3f}% | {kelly_str} | {data.get('risk_of_ruin_pct', 0.0):.1f}% | {extrema_str} | {std_str} | "
            f"{data.get('var_95_pct', 0.0):+.2f}% | {data.get('cvar_95_pct', 0.0):+.2f}% | "
            f"-{data.get('max_drawdown_pct', 0.0):.2f}% | -{data.get('dar_95_pct', 0.0):.2f}% | -{data.get('cdar_95_pct', 0.0):.2f}% | {data.get('cdar_ratio', 0.0):.2f} | "
            f"{data.get('ulcer_index', 0.0):.2f}% | "
            f"{data.get('k_ratio', 0.0):.2f} | "
            f"{data.get('sortino_ratio', 0.0):.2f} | "
            f"{data.get('burke_ratio', 0.0):.2f} | "
            f"{data.get('sterling_ratio', 0.0):.2f} | "
            f"{data.get('gain_to_pain_ratio', 0.0):.2f} | "
            f"{data.get('martin_ratio', 0.0):.2f} | {data.get('calmar_ratio', 0.0):.2f} | {romad_str} | "
            f"{data.get('annualized_calmar', 0.0):.2f} | {data.get('annualized_sharpe', 0.0):.2f} | "
            f"{data.get('cagr_pct', 0.0):+.2f}% | {data.get('backtest_days', 0.0):.0f}일 | "
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

    # Detailed direction breakdown (long vs short)
    for name, data in analysis_results.items():
        directions = data.get("direction_performance", {})
        if directions:
            lines.append("")
            lines.append(f"### ↕️ 전략 `{name}` 롱/숏 포지션 방향별 성과 분석")
            lines.append("| 포지션 방향 | 거래수 | 승률 | 총 수익률 | 평균 수익률 | 손익비(P.F.) | 기대값(bps) | 손익비율 | 최대 이익/손실 | 평균 보유시간 |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
            for side, s in directions.items():
                side_label = "🟢 롱 (Long)" if side == "long" else "🔴 숏 (Short)"
                max_w = s.get("max_win_pct", 0.0)
                max_l = s.get("max_loss_pct", 0.0)
                extrema_str = f"+{max_w:.1f}%/-{max_l:.1f}%"
                lines.append(
                    f"| {side_label} | {s['trades']}회 | {s['win_rate_pct']:.1f}% | "
                    f"{s['total_profit_pct']:+.2f}% | {s['avg_profit_pct']:+.2f}% | "
                    f"{s['profit_factor']:.2f} | {s.get('expectancy_bps', 0.0):+.1f}bp | "
                    f"{s.get('win_loss_ratio', 0.0):.2f} | {extrema_str} | {s['avg_duration_min']:.1f}분 |"
                )

    # Detailed Day of Week performance tables
    for name, data in analysis_results.items():
        dows = data.get("day_of_week_performance", {})
        if dows:
            lines.append("")
            lines.append(f"### 📅 전략 `{name}` 요일별(Day of Week) 거래 성과 분석")
            lines.append("| 요일 | 거래수 | 승률 | 총 수익률 | 평균 수익률 | 손익비(P.F.) | 기대값(bps) | 최대 이익/손실 | 평균 보유시간 |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
            for day, s in dows.items():
                max_w = s.get("max_win_pct", 0.0)
                max_l = s.get("max_loss_pct", 0.0)
                extrema_str = f"+{max_w:.1f}%/-{max_l:.1f}%"
                lines.append(
                    f"| `{day}` | {s['trades']}회 | {s['win_rate_pct']:.1f}% | "
                    f"{s['total_profit_pct']:+.2f}% | {s['avg_profit_pct']:+.2f}% | "
                    f"{s['profit_factor']:.2f} | {s.get('expectancy_bps', 0.0):+.1f}bp | "
                    f"{extrema_str} | {s['avg_duration_min']:.1f}분 |"
                )

    # Detailed Duration Tier performance tables
    for name, data in analysis_results.items():
        tiers = data.get("duration_tier_performance", {})
        if tiers:
            lines.append("")
            lines.append(f"### ⏱️ 전략 `{name}` 포지션 보유 기간 구간별(Duration Tiers) 거래 성과")
            lines.append("| 보유 기간 구간 | 거래수 | 승률 | 총 수익률 | 평균 수익률 | 손익비(P.F.) | 기대값(bps) | 손익비율 | 최대 이익/손실 | 평균 보유시간 |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
            for tier, s in tiers.items():
                max_w = s.get("max_win_pct", 0.0)
                max_l = s.get("max_loss_pct", 0.0)
                extrema_str = f"+{max_w:.1f}%/-{max_l:.1f}%"
                lines.append(
                    f"| `{tier}` | {s['trades']}회 | {s['win_rate_pct']:.1f}% | "
                    f"{s['total_profit_pct']:+.2f}% | {s['avg_profit_pct']:+.2f}% | "
                    f"{s['profit_factor']:.2f} | {s.get('expectancy_bps', 0.0):+.1f}bp | "
                    f"{s.get('win_loss_ratio', 0.0):.2f} | {extrema_str} | {s['avg_duration_min']:.1f}분 |"
                )

    # Detailed Stake Amount Tier performance tables
    for name, data in analysis_results.items():
        stake_tiers = data.get("stake_tier_performance", {})
        if stake_tiers:
            lines.append("")
            lines.append(f"### 💰 전략 `{name}` 포지션 진입 규모별(Stake Amount Tiers) 거래 성과")
            lines.append("| 베팅 규모 구간 | 거래수 | 승률 | 총 수익률 | 평균 수익률 | 손익비(P.F.) | 기대값(bps) | 총 투입 자본 | 자본 비중(%) | 최대 이익/손실 |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
            for tier, s in stake_tiers.items():
                max_w = s.get("max_win_pct", 0.0)
                max_l = s.get("max_loss_pct", 0.0)
                extrema_str = f"+{max_w:.1f}%/-{max_l:.1f}%"
                lines.append(
                    f"| `{tier}` | {s['trades']}회 | {s['win_rate_pct']:.1f}% | "
                    f"{s['total_profit_pct']:+.2f}% | {s['avg_profit_pct']:+.2f}% | "
                    f"{s['profit_factor']:.2f} | {s.get('expectancy_bps', 0.0):+.1f}bp | "
                    f"${s.get('total_stake', 0.0):,.2f} | {s.get('volume_share_pct', 0.0):.1f}% | {extrema_str} |"
                )

    # Detailed Hourly UTC performance tables
    for name, data in analysis_results.items():
        hours = data.get("hourly_performance", {})
        if hours:
            lines.append("")
            lines.append(f"### 🕒 전략 `{name}` 시간대별(Hourly UTC) 거래 성과 분석")
            lines.append("| 시간대 (UTC) | 거래수 | 승률 | 총 수익률 | 평균 수익률 | 손익비(P.F.) | 기대값(bps) | 최대 이익/손실 | 평균 보유시간 |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
            for hour, s in hours.items():
                max_w = s.get("max_win_pct", 0.0)
                max_l = s.get("max_loss_pct", 0.0)
                extrema_str = f"+{max_w:.1f}%/-{max_l:.1f}%"
                lines.append(
                    f"| `{hour}` | {s['trades']}회 | {s['win_rate_pct']:.1f}% | "
                    f"{s['total_profit_pct']:+.2f}% | {s['avg_profit_pct']:+.2f}% | "
                    f"{s['profit_factor']:.2f} | {s.get('expectancy_bps', 0.0):+.1f}bp | "
                    f"{extrema_str} | {s['avg_duration_min']:.1f}분 |"
                )

    # Detailed Monthly calendar performance tables
    for name, data in analysis_results.items():
        months = data.get("monthly_performance", {})
        if months:
            lines.append("")
            lines.append(f"### 📆 전략 `{name}` 월별(Monthly Calendar) 거래 성과 분석")
            lines.append("| 월 (Year-Month) | 거래수 | 승률 | 총 수익률 | 평균 수익률 | 월간 최대낙폭 | 손익비(P.F.) | 기대값(bps) | 손익비율 | 최대 이익/손실 | 평균 보유시간 |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
            for m_key, s in months.items():
                max_w = s.get("max_win_pct", 0.0)
                max_l = s.get("max_loss_pct", 0.0)
                extrema_str = f"+{max_w:.1f}%/-{max_l:.1f}%"
                lines.append(
                    f"| `{m_key}` | {s['trades']}회 | {s['win_rate_pct']:.1f}% | "
                    f"{s['total_profit_pct']:+.2f}% | {s['avg_profit_pct']:+.2f}% | "
                    f"-{s.get('max_drawdown_pct', 0.0):.2f}% | "
                    f"{s['profit_factor']:.2f} | {s.get('expectancy_bps', 0.0):+.1f}bp | "
                    f"{s.get('win_loss_ratio', 0.0):.2f} | {extrema_str} | {s['avg_duration_min']:.1f}분 |"
                )

    # Detailed Drawdown Episodes table
    for name, data in analysis_results.items():
        episodes_info = data.get("drawdown_episodes", {})
        top_eps = episodes_info.get("top_episodes", [])
        if top_eps:
            lines.append("")
            lines.append(f"### 📉 전략 `{name}` 주요 낙폭 에피소드(Drawdown Episodes) TOP 5")
            lines.append("| 순위 | 고점 시점 | 저점 시점 | 회복 시점 | 낙폭(Depth) | 하락 거래수 | 회복 거래수 | 총 침체 거래수 | 회복 상태 |")
            lines.append("| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |")
            for ep in top_eps:
                status_str = "✅ 회복완료" if ep.get("is_recovered") else "⏳ 침체진행중"
                lines.append(
                    f"| {ep['rank']}위 | `{ep['peak_date']}` | `{ep['trough_date']}` | "
                    f"`{ep['recovery_date']}` | -{ep['depth_pct']:.2f}% | "
                    f"{ep['drawdown_trades']}회 | {ep['recovery_trades']}회 | "
                    f"{ep['total_trades']}회 | {status_str} |"
                )

    # Detailed Rolling Window performance stability tables
    has_rolling = any(data.get("rolling_windows_count", 0) > 0 for data in analysis_results.values())
    if has_rolling:
        lines.append("")
        lines.append("### 🔄 전략별 롤링 윈도우(Rolling Window) 성과 안정성 분석")
        lines.append("| 전략명 | 윈도우 크기 | 윈도우 수 | 중위 샤프 | 샤프 범위(Min~Max) | 샤프 표준편차 | 수익 일관성 | 역성장 윈도우 비율 | 롤링 승률 범위 | 최악 롤링 MDD |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for name, data in analysis_results.items():
            if data.get("rolling_windows_count", 0) > 0:
                lines.append(
                    f"| **{name}** | {data.get('rolling_window_size', 30)}거래 | "
                    f"{data.get('rolling_windows_count', 0)}회 | {data.get('rolling_sharpe_median', 0.0):.2f} | "
                    f"{data.get('rolling_sharpe_min', 0.0):.2f} ~ {data.get('rolling_sharpe_max', 0.0):.2f} | "
                    f"{data.get('rolling_sharpe_std', 0.0):.2f} | {data.get('consistency_score_pct', 0.0):.1f}% | "
                    f"{data.get('pct_negative_sharpe_windows', 0.0):.1f}% | "
                    f"{data.get('rolling_win_rate_min_pct', 0.0):.1f}% ~ {data.get('rolling_win_rate_max_pct', 0.0):.1f}% | "
                    f"-{data.get('rolling_mdd_worst_pct', 0.0):.2f}% |"
                )

    # Detailed Slippage and fee sensitivity stress tables
    for name, data in analysis_results.items():
        sens = data.get("slippage_sensitivity", {})
        curve = sens.get("sensitivity_curve", [])
        if curve:
            be_bps = sens.get("breakeven_friction_bps", 0.0)
            rating = sens.get("resilience_rating", "N/A")
            lines.append("")
            lines.append(f"### 📉 전략 `{name}` 슬리피지·수수료 마찰 민감도 스트레스 분석 (Slippage Sensitivity Curve)")
            lines.append(f"- **손익분기 허용 마찰(Breakeven Friction)**: `{be_bps:.1f} bps` ({rating})")
            lines.append("| 추가 마찰 (bps) | 승률 | 총 수익률 | 손익비(P.F.) | 기대값(bps) | 수익 감쇄율(%) |")
            lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
            for row in curve:
                lines.append(
                    f"| `+{row['friction_bps']:.0f} bps` | {row['win_rate_pct']:.1f}% | "
                    f"{row['total_return_pct']:+.2f}% | {row['profit_factor']:.2f} | "
                    f"{row['expectancy_bps']:+.1f}bp | -{row['return_decay_pct']:.1f}% |"
                )

    # Detailed Profit concentration and outlier overfitting tables
    for name, data in analysis_results.items():
        conc = data.get("profit_concentration", {})
        if conc and conc.get("robustness_rating") != "N/A":
            rating = conc.get("robustness_rating", "N/A")
            is_prof_str = "✅ 유지" if conc.get("is_profitable_without_top_3") else "❌ 적자 전락"
            lines.append("")
            lines.append(f"### 🎯 전략 `{name}` 수익 집중도 및 이상치 의존성(Outlier Robustness) 분석")
            lines.append(f"- **이상치 견고성 등급**: `{rating}` (상위 3개 거래 제외 시: {is_prof_str})")
            lines.append("| 지표 항목 | 산출값 | 평가 및 의미 |")
            lines.append("| :--- | :---: | :--- |")
            lines.append(f"| **최대 단일 거래 수익 비중 (Top 1)** | `{conc.get('top_1_profit_share_pct', 0.0):.1f}%` | 1위 거래가 총 수익에 기여한 비중 |")
            lines.append(f"| **상위 3개 거래 수익 비중 (Top 3)** | `{conc.get('top_3_profit_share_pct', 0.0):.1f}%` | 상위 3개 거래의 누적 수익 점유율 |")
            lines.append(f"| **상위 5개 거래 수익 비중 (Top 5)** | `{conc.get('top_5_profit_share_pct', 0.0):.1f}%` | 상위 5개 거래의 누적 수익 점유율 |")
            lines.append(f"| **상위 10% 거래 수익 비중 (Top 10%)** | `{conc.get('top_10pct_profit_share_pct', 0.0):.1f}%` | 상위 10% 거래들의 수익 집중도 |")
            lines.append(f"| **수익 허핀달 지수 (HHI)** | `{conc.get('herfindahl_index', 0.0):.1f}` | 수익 집중도 (HHI < 2500: 정상 분산) |")
            lines.append(f"| **지니 계수 (Gini Coefficient)** | `{conc.get('gini_coefficient', 0.0):.3f}` | 거래 간 수익 불평등도 (0.0: 완전 균등 ~ 1.0: 독점) |")
            lines.append(f"| **1위 거래 제외 수익률** | `{conc.get('profit_without_top_1_pct', 0.0):+.2f}%` | 최고 대박 거래를 놓쳤을 때의 순수익률 |")
            lines.append(f"| **상위 3개 제외 수익률 (Trimmed)** | `{conc.get('profit_without_top_3_pct', 0.0):+.2f}%` | 상위 3개 극단치 제외 시 실질 순수익률 |")
            lines.append(f"| **상위 3개 제외 손익비 (Trimmed P.F.)** | `{conc.get('pf_without_top_3', 0.0):.2f}` | 상위 3개 극단치 제외 시 기초 체력 손익비 |")
            lines.append(f"| **상위 3개 제거 수익 감쇄율** | `-{conc.get('trimmed_profit_decay_pct', 0.0):.1f}%` | 상위 3개 이상치 제거 시 수익 감소 비율 |")

    # Detailed Concurrency and capital exposure tables
    for name, data in analysis_results.items():
        conc_exp = data.get("concurrency_analysis", {})
        if conc_exp and conc_exp.get("capital_efficiency_rating") != "N/A":
            rating = conc_exp.get("capital_efficiency_rating", "N/A")
            peak_c = conc_exp.get("peak_concurrent_trades", 0)
            avg_c = conc_exp.get("avg_concurrent_trades", 0.0)
            idle_p = conc_exp.get("idle_time_pct", 0.0)
            penalty_p = conc_exp.get("correlation_overload_penalty_pct", 0.0)
            lines.append("")
            lines.append(f"### 🔀 전략 `{name}` 동시 보유 포지션(Concurrency) 및 자본 활용도 분석")
            lines.append(f"- **자본 효율성 등급**: `{rating}` (최대 동시 슬롯: `{peak_c}개`, 가중 평균: `{avg_c:.1f}개`, 유휴 현금 시간: `{idle_p:.1f}%`)")
            if penalty_p > 0:
                lines.append(f"- **동시 다발 진입 승률 감쇄(Overload Penalty)**: `-{penalty_p:.1f}%p` (단독 진입 대비 다중 진입 시 승률 하락폭)")
            slots = conc_exp.get("slot_tier_performance", {})
            if slots:
                lines.append("| 동시 진입 밀도 | 거래수 | 승률 | 총 수익률 | 손익비(P.F.) | 기대값(bps) |")
                lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
                for slot_name, s in slots.items():
                    lines.append(
                        f"| **{slot_name}** | {s['trades']}회 | {s['win_rate_pct']:.1f}% | "
                        f"{s['total_profit_pct']:+.2f}% | {s['profit_factor']:.2f} | "
                        f"{s['expectancy_bps']:+.1f}bp |"
                    )

    # Detailed MAE / MFE and Exit Efficiency tables
    for name, data in analysis_results.items():
        mae_mfe = data.get("mae_mfe_analysis", {})
        if mae_mfe and mae_mfe.get("edge_rating") != "N/A":
            lines.append("")
            lines.append(f"### 🎯 전략 `{name}` MAE / MFE 진입 우위(Edge) 및 청산 효율성(Exit Capture) 분석")
            lines.append(f"- **진입 통계적 우위 등급**: `{mae_mfe.get('edge_rating', 'N/A')}` (우위 지수 Edge Ratio: `{mae_mfe.get('edge_ratio', 0.0):.2f}`, MFE/|MAE| 비율)")
            lines.append(f"- **승리 거래 청산 효율성**: `{mae_mfe.get('avg_win_capture_pct', 0.0):.1f}%` (최대 도달 수익 대비 실제 실현 수익의 회수율)")
            lines.append(f"- **권장 스탑로스(Optimal SL)**: `-{mae_mfe.get('optimal_sl_suggestion_pct', 0.0):.2f}%` (승리 거래의 95% 분위수 역방향 진폭 기준 노이즈 털림 방지선)")
            wasted_p = mae_mfe.get("wasted_winners_pct", 0.0)
            if wasted_p > 0:
                lines.append(f"- **수익 반납 후 손절 비율(Wasted Winners)**: `{wasted_p:.1f}%` ({mae_mfe.get('wasted_winners_count', 0)}회, +1.0% 이상 도달 후 손실 마감된 거래)")
            lines.append("| 지표 항목 | 전체 거래 | 승리 거래 (Wins) | 패배 거래 (Losses) |")
            lines.append("| :--- | :---: | :---: | :---: |")
            lines.append(f"| **평균 최대 역행 진폭 (Avg MAE)** | `{mae_mfe.get('avg_mae_pct', 0.0):+.2f}%` | `{mae_mfe.get('avg_win_mae_pct', 0.0):+.2f}%` | `{mae_mfe.get('avg_loss_mae_pct', 0.0):+.2f}%` |")
            lines.append(f"| **평균 최대 순행 진폭 (Avg MFE)** | `{mae_mfe.get('avg_mfe_pct', 0.0):+.2f}%` | `{mae_mfe.get('avg_win_mfe_pct', 0.0):+.2f}%` | `{mae_mfe.get('avg_loss_mfe_pct', 0.0):+.2f}%` |")

    # Detailed Monte Carlo sequence risk tables
    has_mc = any(data.get("mc_iterations", 0) > 0 for data in analysis_results.values())
    if has_mc:
        lines.append("")
        lines.append("### 🎲 몬테카를로 무작위 거래 순서 시뮬레이션 (Sequence of Returns Risk)")
        lines.append("| 전략명 | 시뮬레이션 | 평균 MDD | 50% 중위 MDD | 95% 최악 MDD | 99% 스트레스 MDD | 최대 관측 MDD | 위험 임계치 | 임계치 초과 확률 |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for name, data in analysis_results.items():
            if data.get("mc_iterations", 0) > 0:
                lines.append(
                    f"| **{name}** | {data.get('mc_iterations', 0):,}회 | "
                    f"-{data.get('mc_mdd_mean_pct', 0.0):.2f}% | -{data.get('mc_mdd_median_pct', 0.0):.2f}% | "
                    f"-{data.get('mc_mdd_95_pct', 0.0):.2f}% | -{data.get('mc_mdd_99_pct', 0.0):.2f}% | "
                    f"-{data.get('mc_mdd_max_pct', 0.0):.2f}% | {data.get('mc_ruin_threshold_pct', 20.0):.1f}% | "
                    f"{data.get('mc_prob_mdd_exceed_pct', 0.0):.2f}% |"
                )

    lines.append("")
    lines.append("### 💡 지표 설명 (Methodology)")
    lines.append("- **동시 보유 포지션 및 자본 활용도 (Concurrency & Capital Exposure)**: 백테스트 기간 중 동시에 열려 있던 활성 포지션 수의 시간 가중 평균 및 최대 동시 진입 슬롯(Peak Concurrent Slots)을 추적합니다. 자본이 거래 없이 방치된 유휴 시간 비율(Idle Time %)과 다중 포지션 동시 보유 시 발생하는 시장 충격 동반 손절(Correlated Overload Penalty)을 진단합니다.")
    lines.append("- **수익 집중도 및 이상치 의존성 (Profit Concentration & Outlier Robustness)**: 소수의 대박(Outlier) 거래가 전체 성과를 왜곡했는지 검증하는 분석입니다. 상위 3개 거래를 완전히 제거했을 때도 전략이 여전히 흑자를 유지하는지(Trimmed Net Profit & PF), 그리고 수익 허핀달 지수(HHI)와 지니 계수(Gini)를 측정하여 지속 가능한 유기적 알파인지 과최적화된 요행인지를 엄격히 판별합니다.")
    lines.append("- **시스템 품질 지수 (System Quality Number / SQN, Van Tharp)**: sqrt(N) * (평균 수익률 / 수익률 표준편차). 거래 전략의 통계적 우수성을 종합 평가하는 지표로, 2.0 이상이면 평균, 3.0 이상이면 우수(Excellent), 5.0 이상이면 탁월(Superb), 7.0 이상이면 성배(Holy Grail) 등급으로 분류됩니다.")
    lines.append("- **K-비율 (K-Ratio, Lars Kestner)**: 누적 수익 곡선의 선형 추세 기울기를 표준오차와 sqrt(T)로 정규화한 지표로, 수익 곡선이 노이즈 없이 얼마나 일관되게 우상향하는지 측정합니다.")
    lines.append("- **테일 비율 (Tail Ratio)**: 95분위수 수익률 / 5분위수 손실률 절대값 (p95 / |p05|). 1.0 초과 시 우측 꼬리(수익)가 좌측 꼬리(손실)보다 비대칭적으로 우세함을 의미합니다.")
    lines.append("- **상식 비율 (Common Sense Ratio / CSR)**: 손익비(Profit Factor) × 테일 비율(Tail Ratio). 트레이딩 엣지가 단지 대칭적 분산에 의한 것이 아니라 진정한 비대칭 우위에 기반하는지 측정하는 복합 척도입니다.")
    lines.append("- **궤양지수 (Ulcer Index, Peter Martin 1987)**: 고점 대비 하락폭(Drawdown)의 제곱평균제곱근(RMS). 단순 변동성과 달리 상승 변동성은 처벌하지 않고 깊고 긴 하락장만을 집중 가중 처벌합니다.")
    lines.append("- **마틴 비율 (Martin Ratio / UPI)**: 총 수익률을 궤양지수로 나눈 값으로, 샤프 지수보다 추세추종 전략의 실질 하방 위험 대비 성과를 정확하게 평가합니다.")
    lines.append("- **소르티노 비율 (Sortino Ratio)**: 하방 변동성(Downside Deviation)만을 페널티로 부여하여 하방 손실 위험 대비 전략의 초과 수익률을 평가합니다.")
    lines.append("- **버크 비율 (Burke Ratio, Gibbons Burke 1994)**: 총 수익률을 개별 낙폭(Drawdown)들의 제곱합의 제곱근으로 나눈 비율로, 단일 극단값뿐 아니라 누적된 다수의 하락 충격을 종합 반영합니다.")
    lines.append("- **스털링 비율 (Sterling Ratio)**: 총 수익률을 평균 낙폭(Average Drawdown)으로 나눈 값으로, 일상적인 조정 깊이 대비 수익 창출력을 측정합니다.")
    lines.append("- **게인 투 페인 비율 (Gain-to-Pain Ratio, Jack Schwager)**: 전체 거래 순손익률의 합을 손실 거래 손실률 절대값의 합으로 나눈 비율로, 감내한 하방 고통(손실액) 대비 누적 창출 수익의 효율성을 직관적으로 평가합니다.")
    lines.append("- **수중 기간 비율 (Time Underwater %)**: 전체 거래 중 최고점(High-Water Mark)을 탈환하지 못하고 손실 구간에 머무른 거래 수의 백분율입니다.")
    lines.append("- **켈리 비율 (Kelly Criterion, Full/Half)**: 승률과 손익비를 바탕으로 자본 성장을 극대화하는 이론적 최적 베팅 비중(f*) 및 암호화폐 시장의 꼬리 위험을 완화한 보수적 권장치인 하프 켈리(Half-Kelly, f*/2) 비율입니다.")
    lines.append("- **파산 위험률 (Risk of Ruin, Ralph Vince & Perry Kaufman)**: 50% 자본 손실(계좌 반토막) 한계에 도달할 이론적 파산 확률을 측정하는 척도로, 승률, 손익비 및 하프 켈리 베팅 비중을 반영하여 장기 생존 가능성을 정량화합니다.")
    lines.append("- **거래 기대값 (Trade Expectancy)**: (승률 × 평균 수익률) - (패율 × 평균 손실률). 1회 거래당 기대되는 통계적 엣지(Edge)입니다.")
    lines.append("- **청산 사유 분석 (Exit Breakdown)**: 각 커스텀 청산 태그(RSI 과매수, 손절, 익절 등)의 개별 승률과 평균 보유 기간을 분리 집계하여 취약한 청산 로직을 진단합니다.")
    lines.append("- **페어별 성과 분석 (Pair Performance)**: 거래 코인 페어별 승률, 누적 수익률, 손익비 및 보유시간을 비교하여 전략에 유리하거나 불리한 자산을 식별합니다.")
    lines.append("- **롱/숏 포지션 성과 분석 (Direction Breakdown)**: 롱(Long) 및 숏(Short) 포지션 진입 방향별 거래수, 승률, 누적 수익률, 손익비를 분리 평가하여 시장 방향성 의존도를 점검합니다.")
    lines.append("- **수익률 왜도 (Skewness)**: 거래별 손익률 분포의 비대칭성을 나타내며, 0보다 크면(양의 왜도) 이익 거래의 꼬리가 길어 손익비가 우수한 추세추종 전략의 특성을 보이고, 0보다 작으면(음의 왜도) 승률은 높으나 급락 위험(Left-tail risk)이 있는 역추세 전략의 특성을 나타냅니다.")
    lines.append("- **초과 첨도 (Excess Kurtosis)**: 정규분포(0.0) 대비 극단치(Fat-tail) 발생 가능성을 측정하며, 양수이면 이상치(대박 또는 대형 손실) 거래가 빈번하게 발생하는 팻 테일 분포임을 의미합니다.")
    lines.append("- **보유시간 비대칭도 (Win/Loss Duration Ratio)**: 수익 거래 평균 보유시간 / 손실 거래 평균 보유시간. 1.0 이상이면 손실을 빠르게 끊고 이익을 길게 가져가는(Let winners run, cut losers) 바람직한 추세추종 특성을 나타냅니다.")
    lines.append("- **회복 계수 (Recovery Factor)**: 총 순수익률을 최대 낙폭(MDD)으로 나눈 값으로, 감내한 최대 하방 위험 대비 얼마만큼의 자본 증식을 달성했는지 평가합니다.")
    lines.append("- **최대 침체 기간 (Max Underwater Trades)**: 고점 갱신 후 새로운 고점을 탈환하지 못하고 지속된 최장 연속 거래 횟수입니다.")
    lines.append("- **VaR 및 CVaR (Value at Risk & Expected Shortfall)**: 95% 및 99% 신뢰수준에서의 단일 거래 최대 예상 손실률(VaR)과 꼬리 위험 발생 시의 평균 손실폭(CVaR / Expected Shortfall)으로, 극단적 시장 충격(Black Swan)에 대한 전략의 방어력을 정량 평가합니다.")
    lines.append("- **DaR 및 CDaR (Drawdown at Risk & Conditional Drawdown at Risk, Chekhlov, Uryasev, Zabarankin)**: 95% 신뢰수준에서의 낙폭 깊이(DaR 95%)와 이를 초과하는 최악 5% 낙폭들의 조건부 평균 깊이(CDaR 95%)로, 단일 틱 극단치에 취약한 최대 낙폭(MDD)의 한계를 극복한 일관된(coherent) 하방 위험 척도입니다.")
    lines.append("- **CDaR 비율 (CDaR Ratio)**: 총 수익률을 CDaR(95%)로 나눈 위험조정 수익률로, 전통적인 칼마 비율(Calmar Ratio)보다 극단치 왜곡이 적고 통계적 신뢰도가 높습니다.")
    lines.append("- **최대 단일 이익/손실 (Max Win / Max Loss %)**: 백테스트 기간 중 단일 거래에서 발생한 최대 수익률과 최대 손실률로, 극단치 거래에 대한 전략의 의존도를 식별합니다.")
    lines.append("- **수익률 표준편차 (Trade Return Std Dev)**: 개별 거래 손익률의 분산 정도로, 개별 거래 결과의 변동폭과 위험 노출도를 측정합니다.")
    lines.append("- **연평균 복리 성장률 (CAGR / Compound Annual Growth Rate)**: 백테스트 총 기간(일수)을 반영하여 연간 기준으로 환산한 복리 수익률입니다.")
    lines.append("- **MAR 비율 (MAR Ratio)**: 연평균 복리 수익률(CAGR)을 최대 낙폭(MDD)으로 나눈 값으로, CTA 및 선물 헤지펀드에서 중장기 리스크 대비 성장성을 엄격히 평가하는 대표 지표입니다.")
    lines.append("- **연환산 샤프 비율 (Annualized Sharpe Ratio)**: 연간 거래 빈도(Trades/Year)의 제곱근을 적용하여 거래당 위험조정 수익률을 1년 기준으로 표준화한 기관 투자 지표입니다.")
    lines.append("- **연환산 칼마 비율 (Annualized Calmar Ratio)**: 연평균 복리 수익률(CAGR)을 최대 낙폭(MDD)으로 나눈 값으로, 연간 자본 성장률 대비 하방 위험을 정량 평가합니다.")
    lines.append("- **연승/연패 비대칭도 (Streak Asymmetry Ratio)**: 최대 연속 수익 횟수를 최대 연속 손실 횟수로 나눈 비율로, 1.0 초과 시 연패 리스크 대비 연승 모멘텀 지속력이 우세함을 나타냅니다.")
    lines.append("- **런 검정 (Wald-Wolfowitz Runs Test Z-Score, Perry Kaufman)**: 연속된 거래 결과(승/패)의 계열 상관성을 검정하는 통계량으로, Z < -1.96이면 연승/연패 군집(Clustering) 현상을, Z > 1.96이면 승패 교번(Mean-reversion) 특성을, |Z| <= 1.96이면 거래 결과가 통계적으로 독립적임을 나타냅니다.")
    lines.append("- **CPC 지수 (Continuation Protection Criterion)**: 손익비 × 승률 × 손익비율(Win/Loss Ratio)의 복합 척도로, 전략의 장기적인 수익성 지속력을 검증합니다.")
    lines.append("- **RoMaD (Return over Maximum Drawdown)**: 총 누적 수익률을 최대 낙폭(MDD)으로 나눈 지표로, 헤지펀드 및 퀀트 자산배분에서 최대 감내 손실 대비 자본 수익 배수를 직관적으로 평가합니다.")
    lines.append("- **최대 역행/순행 진폭 및 청산 효율성 (MAE / MFE & Exit Capture Efficiency)**: 각 거래가 진행되는 동안 경험한 최악의 장중 낙폭(MAE, Maximum Adverse Excursion)과 최고의 장중 미실현 수익(MFE, Maximum Favorable Excursion)을 추적합니다. 진입 우위 지수(Edge Ratio = MFE / |MAE|)를 통해 진입 시점의 통계적 우위를 검증하고, 최고점 대비 실제 실현된 수익 비율(Exit Capture %) 및 수익 구간 도달 후 손절로 전환된 거래(Wasted Winners)를 진단하여 최적 스탑로스 배치 기준선을 제시합니다.")
    lines.append("- **몬테카를로 무작위 재배열 시뮬레이션 (Monte Carlo Trade Reshuffle)**: 과거 백테스트 거래들의 순서를 무작위로 수천 번 재배열(Permutation)하여 거래 순서 의존성(Sequence of Returns Risk)을 검증하고, 최악의 연패 구간이 겹쳤을 때 발생 가능한 95% 및 99% 신뢰구간의 잠재적 최대 낙폭(Worst Expected MDD)과 계좌 파산/위험 임계치 초과 확률을 도출합니다.")
    return "\n".join(lines)


def export_quant_analysis_csv(analysis_results: dict[str, Any]) -> str:
    """Export strategy analysis summary as a formatted CSV string."""
    headers = [
        "strategy",
        "total_trades",
        "win_rate_pct",
        "wins",
        "losses",
        "draws",
        "max_consecutive_wins",
        "max_consecutive_losses",
        "streak_ratio",
        "runs_test_zscore",
        "runs_test_rating",
        "profit_factor",
        "cpc_index",
        "sqn",
        "sqn_100",
        "sqn_rating",
        "skewness",
        "kurtosis",
        "tail_ratio",
        "common_sense_ratio",
        "expectancy_pct",
        "expectancy_bps",
        "avg_win_pct",
        "avg_loss_pct",
        "max_win_pct",
        "max_loss_pct",
        "std_profit_pct",
        "median_profit_pct",
        "p25_profit_pct",
        "p75_profit_pct",
        "iqr_profit_pct",
        "win_loss_ratio",
        "win_loss_count_ratio",
        "avg_duration_min",
        "avg_win_duration_min",
        "avg_loss_duration_min",
        "win_loss_duration_ratio",
        "full_kelly_pct",
        "half_kelly_pct",
        "risk_of_ruin_pct",
        "total_return_pct",
        "max_drawdown_pct",
        "ulcer_index",
        "pain_index",
        "k_ratio",
        "sortino_ratio",
        "burke_ratio",
        "sterling_ratio",
        "gain_to_pain_ratio",
        "omega_ratio",
        "martin_ratio",
        "calmar_ratio",
        "romad_ratio",
        "annualized_calmar",
        "mar_ratio",
        "annualized_sharpe",
        "cagr_pct",
        "backtest_days",
        "recovery_factor",
        "downside_deviation_pct",
        "time_underwater_pct",
        "avg_drawdown_pct",
        "max_drawdown_duration_trades",
        "avg_recovery_trades",
        "max_recovery_trades",
        "total_drawdown_episodes",
        "worst_dd_depth_pct",
        "worst_dd_trades",
        "rolling_window_size",
        "rolling_windows_count",
        "rolling_sharpe_median",
        "rolling_sharpe_std",
        "rolling_sharpe_min",
        "rolling_sharpe_max",
        "rolling_win_rate_min_pct",
        "rolling_win_rate_max_pct",
        "rolling_mdd_worst_pct",
        "pct_negative_sharpe_windows",
        "consistency_score_pct",
        "var_95_pct",
        "cvar_95_pct",
        "var_99_pct",
        "cvar_99_pct",
        "dar_95_pct",
        "cdar_95_pct",
        "cdar_ratio",
        "mc_iterations",
        "mc_mdd_mean_pct",
        "mc_mdd_median_pct",
        "mc_mdd_95_pct",
        "mc_mdd_99_pct",
        "mc_mdd_max_pct",
        "mc_ruin_threshold_pct",
        "mc_prob_mdd_exceed_pct",
        "breakeven_friction_bps",
        "slippage_resilience_rating",
        "top_1_profit_share_pct",
        "top_3_profit_share_pct",
        "top_5_profit_share_pct",
        "top_10pct_profit_share_pct",
        "herfindahl_index",
        "gini_coefficient",
        "profit_without_top_1_pct",
        "profit_without_top_3_pct",
        "pf_without_top_3",
        "is_profitable_without_top_3",
        "trimmed_profit_decay_pct",
        "concentration_robustness_rating",
        "peak_concurrent_trades",
        "avg_concurrent_trades",
        "idle_time_pct",
        "capital_efficiency_rating",
        "correlation_overload_penalty_pct",
        "avg_mae_pct",
        "avg_mfe_pct",
        "avg_win_mae_pct",
        "avg_win_mfe_pct",
        "avg_win_capture_pct",
        "avg_loss_mae_pct",
        "avg_loss_mfe_pct",
        "wasted_winners_count",
        "wasted_winners_pct",
        "edge_ratio",
        "optimal_sl_suggestion_pct",
        "edge_rating",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for name, data in analysis_results.items():
        row = dict(data)
        row["strategy"] = name
        writer.writerow(row)
    return output.getvalue()


def generate_html_report(analysis_results: dict[str, Any]) -> str:
    """Generate standalone interactive HTML quant report from backtest analysis results."""
    sections = []
    for name, data in analysis_results.items():
        total_trades = data.get("total_trades", 0)
        win_rate = data.get("win_rate_pct", 0.0)
        pf = data.get("profit_factor", 0.0)
        tail_ratio = data.get("tail_ratio", 0.0)
        csr = data.get("common_sense_ratio", 0.0)
        expectancy = data.get("expectancy_pct", 0.0)
        total_ret = data.get("total_return_pct", 0.0)
        mdd = data.get("max_drawdown_pct", 0.0)
        ulcer = data.get("ulcer_index", 0.0)
        martin = data.get("martin_ratio", 0.0)
        sortino = data.get("sortino_ratio", 0.0)
        burke = data.get("burke_ratio", 0.0)
        sterling = data.get("sterling_ratio", 0.0)
        gain_to_pain = data.get("gain_to_pain_ratio", 0.0)
        full_kelly = data.get("full_kelly_pct", 0.0)
        half_kelly = data.get("half_kelly_pct", 0.0)
        risk_of_ruin = data.get("risk_of_ruin_pct", 0.0)
        backtest_days = data.get("backtest_days", 0.0)
        cagr = data.get("cagr_pct", 0.0)
        ann_sharpe = data.get("annualized_sharpe", 0.0)
        ann_calmar = data.get("annualized_calmar", 0.0)
        underwater = data.get("time_underwater_pct", 0.0)
        max_streak = f"{data.get('max_consecutive_wins', 0)}W / {data.get('max_consecutive_losses', 0)}L"
        sqn = data.get("sqn", 0.0)
        sqn_rating = data.get("sqn_rating", "N/A")
        k_ratio = data.get("k_ratio", 0.0)
        omega = data.get("omega_ratio", 0.0)
        var_95 = data.get("var_95_pct", 0.0)
        cvar_95 = data.get("cvar_95_pct", 0.0)
        dar_95 = data.get("dar_95_pct", 0.0)
        cdar_95 = data.get("cdar_95_pct", 0.0)
        cdar_ratio = data.get("cdar_ratio", 0.0)
        max_win = data.get("max_win_pct", 0.0)
        max_loss = data.get("max_loss_pct", 0.0)
        std_profit = data.get("std_profit_pct", 0.0)
        streak_ratio = data.get("streak_ratio", 0.0)
        cpc_index = data.get("cpc_index", 0.0)
        runs_z = data.get("runs_test_zscore", 0.0)
        runs_rating = data.get("runs_test_rating", "N/A")
        romad = data.get("romad_ratio", 0.0)
        mar_val = data.get("mar_ratio", 0.0)
        exp_bps = data.get("expectancy_bps", 0.0)

        mc_iter = data.get("mc_iterations", 0)
        mc_95 = data.get("mc_mdd_95_pct", 0.0)
        mc_99 = data.get("mc_mdd_99_pct", 0.0)
        mc_prob = data.get("mc_prob_mdd_exceed_pct", 0.0)
        mc_thresh = data.get("mc_ruin_threshold_pct", 20.0)
        mc_cards = ""
        if mc_iter > 0:
            mc_cards = f"""
            <div class="metric-card">
                <div class="metric-label">몬테카를로 95% 최악 MDD</div>
                <div class="metric-value negative">-{mc_95:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">몬테카를로 99% 스트레스 MDD</div>
                <div class="metric-value negative">-{mc_99:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">낙폭 임계치({mc_thresh:.0f}%) 초과 확률</div>
                <div class="metric-value {('negative' if mc_prob > 10.0 else 'positive')}">{mc_prob:.1f}%</div>
            </div>"""

        if sqn >= 3.0:
            sqn_badge_cls = "badge-success"
        elif sqn >= 2.0:
            sqn_badge_cls = "badge-primary"
        elif sqn >= 1.6:
            sqn_badge_cls = "badge-warning"
        else:
            sqn_badge_cls = "badge-danger"

        if omega >= 2.0:
            omega_badge_cls = "badge-success"
            omega_rating = "Superb"
        elif omega >= 1.5:
            omega_badge_cls = "badge-primary"
            omega_rating = "Strong"
        elif omega >= 1.0:
            omega_badge_cls = "badge-warning"
            omega_rating = "Acceptable"
        else:
            omega_badge_cls = "badge-danger"
            omega_rating = "Sub-optimal"

        skewness = data.get("skewness", 0.0)
        kurtosis = data.get("kurtosis", 0.0)

        if skewness > 0.5:
            skew_badge_cls = "badge-success"
            skew_rating = "Right-Tailed"
        elif skewness < -0.5:
            skew_badge_cls = "badge-danger"
            skew_rating = "Left-Tailed"
        else:
            skew_badge_cls = "badge-primary"
            skew_rating = "Symmetric"

        if kurtosis > 1.0:
            kurt_badge_cls = "badge-warning"
            kurt_rating = "Fat-Tailed"
        elif kurtosis < -1.0:
            kurt_badge_cls = "badge-muted"
            kurt_rating = "Thin-Tailed"
        else:
            kurt_badge_cls = "badge-primary"
            kurt_rating = "Mesokurtic"

        cards_html = f"""
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">총 거래수 / 승률</div>
                <div class="metric-value">{total_trades}회 <span class="badge badge-primary">{win_rate:.1f}%</span></div>
            </div>
            <div class="metric-card">
                <div class="metric-label">손익비 (Profit Factor)</div>
                <div class="metric-value">{pf:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">시스템 품질 지수 (SQN)</div>
                <div class="metric-value">{sqn:.2f} <span class="badge {sqn_badge_cls}">{sqn_rating}</span></div>
            </div>
            <div class="metric-card">
                <div class="metric-label">K-비율 (K-Ratio / Lars Kestner)</div>
                <div class="metric-value">{k_ratio:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">오메가 비율 (Omega Ratio)</div>
                <div class="metric-value">{omega:.2f} <span class="badge {omega_badge_cls}">{omega_rating}</span></div>
            </div>
            <div class="metric-card">
                <div class="metric-label">수익률 왜도 (Skewness)</div>
                <div class="metric-value">{skewness:+.2f} <span class="badge {skew_badge_cls}">{skew_rating}</span></div>
            </div>
            <div class="metric-card">
                <div class="metric-label">초과 첨도 (Excess Kurtosis)</div>
                <div class="metric-value">{kurtosis:+.2f} <span class="badge {kurt_badge_cls}">{kurt_rating}</span></div>
            </div>
            <div class="metric-card">
                <div class="metric-label">테일 비율 (Tail Ratio)</div>
                <div class="metric-value">{tail_ratio:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">상식 비율 (CSR)</div>
                <div class="metric-value">{csr:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">거래 기대값 (Expectancy)</div>
                <div class="metric-value {('positive' if expectancy >= 0 else 'negative')}">{expectancy:+.3f}% <span class="badge {('badge-success' if expectancy >= 0 else 'badge-danger')}">{exp_bps:+.1f} bps</span></div>
            </div>
            <div class="metric-card">
                <div class="metric-label">누적 수익률</div>
                <div class="metric-value {('positive' if total_ret >= 0 else 'negative')}">{total_ret:+.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">최대 낙폭 (Max Drawdown)</div>
                <div class="metric-value negative">-{mdd:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">궤양지수 (Ulcer Index)</div>
                <div class="metric-value">{ulcer:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">마틴 비율 (Martin / UPI)</div>
                <div class="metric-value">{martin:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">소르티노 비율 (Sortino)</div>
                <div class="metric-value">{sortino:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">버크 비율 (Burke)</div>
                <div class="metric-value">{burke:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">스털링 비율 (Sterling)</div>
                <div class="metric-value">{sterling:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">게인 투 페인 (Gain-to-Pain)</div>
                <div class="metric-value">{gain_to_pain:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">켈리 비율 (Full / Half)</div>
                <div class="metric-value">{full_kelly:.1f}% / {half_kelly:.1f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">파산 위험률 (Risk of Ruin)</div>
                <div class="metric-value {('negative' if risk_of_ruin > 10.0 else 'positive')}">{risk_of_ruin:.1f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">연평균 복리 수익률 (CAGR)</div>
                <div class="metric-value {('positive' if cagr >= 0 else 'negative')}">{cagr:+.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">연환산 샤프 (Ann. Sharpe)</div>
                <div class="metric-value">{ann_sharpe:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">연환산 칼마 (Ann. Calmar)</div>
                <div class="metric-value">{ann_calmar:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">MAR 비율 (CAGR / MDD)</div>
                <div class="metric-value">{mar_val:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">백테스트 기간 (Backtest Days)</div>
                <div class="metric-value">{backtest_days:.0f}일</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">최대 연승/연패</div>
                <div class="metric-value">{max_streak}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">수중 기간 (Underwater)</div>
                <div class="metric-value">{underwater:.1f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">VaR (95% 신뢰수준)</div>
                <div class="metric-value {('positive' if var_95 >= 0 else 'negative')}">{var_95:+.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">CVaR (Expected Shortfall)</div>
                <div class="metric-value {('positive' if cvar_95 >= 0 else 'negative')}">{cvar_95:+.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">DaR (95% Drawdown-at-Risk)</div>
                <div class="metric-value negative">-{dar_95:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">CDaR (조건부 낙폭)</div>
                <div class="metric-value negative">-{cdar_95:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">CDaR 비율 (CDaR Ratio)</div>
                <div class="metric-value">{cdar_ratio:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">최대 단일 이익 / 손실</div>
                <div class="metric-value">+{max_win:.1f}% / -{max_loss:.1f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">수익률 표준편차 (Std Dev)</div>
                <div class="metric-value">{std_profit:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">연승/연패 비대칭도 (Streak Ratio)</div>
                <div class="metric-value">{streak_ratio:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">런 검정 (Runs Test Z)</div>
                <div class="metric-value">{runs_z:+.2f} ({runs_rating})</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">CPC 지수 (Continuation Criterion)</div>
                <div class="metric-value">{cpc_index:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">RoMaD (Return over Max DD)</div>
                <div class="metric-value">{romad:.2f}</div>
            </div>
            {mc_cards}
        </div>
        """

        directions = data.get("direction_performance", {})
        dir_rows = []
        for side, s in directions.items():
            tot_p = s.get('total_profit_pct', 0.0)
            avg_p = s.get('avg_profit_pct', 0.0)
            exp_bps = s.get('expectancy_bps', 0.0)
            wl_ratio = s.get('win_loss_ratio', 0.0)
            side_badge = '<span class="badge badge-success">롱 (Long)</span>' if side == 'long' else '<span class="badge badge-danger">숏 (Short)</span>'
            dir_rows.append(f"""
            <tr>
                <td>{side_badge}</td>
                <td>{s.get('trades', 0)}</td>
                <td>{s.get('win_rate_pct', 0.0):.1f}%</td>
                <td class="{('positive' if tot_p >= 0 else 'negative')}">{tot_p:+.2f}%</td>
                <td class="{('positive' if avg_p >= 0 else 'negative')}">{avg_p:+.2f}%</td>
                <td>{s.get('profit_factor', 0.0):.2f}</td>
                <td class="{('positive' if exp_bps >= 0 else 'negative')}">{exp_bps:+.1f}bp</td>
                <td>{wl_ratio:.2f}</td>
                <td>{s.get('avg_duration_min', 0.0):.1f}분</td>
            </tr>
            """)
        dir_table_html = f"""
        <h3>↕️ 롱/숏 포지션 방향별 성과</h3>
        <table>
            <thead>
                <tr><th>포지션 방향</th><th>거래수</th><th>승률</th><th>총 수익률</th><th>평균 수익률</th><th>손익비</th><th>기대값</th><th>손익비율</th><th>평균 보유시간</th></tr>
            </thead>
            <tbody>
                {''.join(dir_rows) if dir_rows else '<tr><td colspan="9">방향 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if directions else ""

        dows = data.get("day_of_week_performance", {})
        dow_rows = []
        for day, s in dows.items():
            tot_p = s.get('total_profit_pct', 0.0)
            avg_p = s.get('avg_profit_pct', 0.0)
            exp_bps = s.get('expectancy_bps', 0.0)
            dow_rows.append(f"""
            <tr>
                <td><strong>{day}</strong></td>
                <td>{s.get('trades', 0)}</td>
                <td>{s.get('win_rate_pct', 0.0):.1f}%</td>
                <td class="{('positive' if tot_p >= 0 else 'negative')}">{tot_p:+.2f}%</td>
                <td class="{('positive' if avg_p >= 0 else 'negative')}">{avg_p:+.2f}%</td>
                <td>{s.get('profit_factor', 0.0):.2f}</td>
                <td class="{('positive' if exp_bps >= 0 else 'negative')}">{exp_bps:+.1f}bp</td>
                <td>{s.get('avg_duration_min', 0.0):.1f}분</td>
            </tr>
            """)
        dow_table_html = f"""
        <h3>📅 요일별(Day of Week) 거래 성과</h3>
        <table>
            <thead>
                <tr><th>요일</th><th>거래수</th><th>승률</th><th>총 수익률</th><th>평균 수익률</th><th>손익비</th><th>기대값</th><th>평균 보유시간</th></tr>
            </thead>
            <tbody>
                {''.join(dow_rows) if dow_rows else '<tr><td colspan="8">요일 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if dows else ""

        tiers = data.get("duration_tier_performance", {})
        tier_rows = []
        for tier, s in tiers.items():
            tot_p = s.get('total_profit_pct', 0.0)
            avg_p = s.get('avg_profit_pct', 0.0)
            exp_bps = s.get('expectancy_bps', 0.0)
            tier_rows.append(f"""
            <tr>
                <td><strong>{tier}</strong></td>
                <td>{s.get('trades', 0)}</td>
                <td>{s.get('win_rate_pct', 0.0):.1f}%</td>
                <td class="{('positive' if tot_p >= 0 else 'negative')}">{tot_p:+.2f}%</td>
                <td class="{('positive' if avg_p >= 0 else 'negative')}">{avg_p:+.2f}%</td>
                <td>{s.get('profit_factor', 0.0):.2f}</td>
                <td class="{('positive' if exp_bps >= 0 else 'negative')}">{exp_bps:+.1f}bp</td>
                <td>{s.get('avg_duration_min', 0.0):.1f}분</td>
            </tr>
            """)
        tier_table_html = f"""
        <h3>⏱️ 포지션 보유 기간 구간별(Duration Tiers) 거래 성과</h3>
        <table>
            <thead>
                <tr><th>보유 기간 구간</th><th>거래수</th><th>승률</th><th>총 수익률</th><th>평균 수익률</th><th>손익비</th><th>기대값</th><th>평균 보유시간</th></tr>
            </thead>
            <tbody>
                {''.join(tier_rows) if tier_rows else '<tr><td colspan="8">구간 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if tiers else ""

        stake_tiers = data.get("stake_tier_performance", {})
        stake_rows = []
        for tier, s in stake_tiers.items():
            tot_p = s.get('total_profit_pct', 0.0)
            avg_p = s.get('avg_profit_pct', 0.0)
            exp_bps = s.get('expectancy_bps', 0.0)
            stake_rows.append(f"""
            <tr>
                <td><strong>{tier}</strong></td>
                <td>{s.get('trades', 0)}</td>
                <td>{s.get('win_rate_pct', 0.0):.1f}%</td>
                <td class="{('positive' if tot_p >= 0 else 'negative')}">{tot_p:+.2f}%</td>
                <td class="{('positive' if avg_p >= 0 else 'negative')}">{avg_p:+.2f}%</td>
                <td>{s.get('profit_factor', 0.0):.2f}</td>
                <td class="{('positive' if exp_bps >= 0 else 'negative')}">{exp_bps:+.1f}bp</td>
                <td>${s.get('total_stake', 0.0):,.2f}</td>
                <td>{s.get('volume_share_pct', 0.0):.1f}%</td>
            </tr>
            """)
        stake_table_html = f"""
        <h3>💰 포지션 진입 규모별(Stake Amount Tiers) 거래 성과</h3>
        <table>
            <thead>
                <tr><th>베팅 규모 구간</th><th>거래수</th><th>승률</th><th>총 수익률</th><th>평균 수익률</th><th>손익비</th><th>기대값</th><th>총 투입 자본</th><th>자본 비중</th></tr>
            </thead>
            <tbody>
                {''.join(stake_rows) if stake_rows else '<tr><td colspan="9">베팅 규모 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if stake_tiers else ""

        hours = data.get("hourly_performance", {})
        hour_rows = []
        for hour, s in hours.items():
            tot_p = s.get('total_profit_pct', 0.0)
            avg_p = s.get('avg_profit_pct', 0.0)
            exp_bps = s.get('expectancy_bps', 0.0)
            hour_rows.append(f"""
            <tr>
                <td><strong>{hour}</strong></td>
                <td>{s.get('trades', 0)}</td>
                <td>{s.get('win_rate_pct', 0.0):.1f}%</td>
                <td class="{('positive' if tot_p >= 0 else 'negative')}">{tot_p:+.2f}%</td>
                <td class="{('positive' if avg_p >= 0 else 'negative')}">{avg_p:+.2f}%</td>
                <td>{s.get('profit_factor', 0.0):.2f}</td>
                <td class="{('positive' if exp_bps >= 0 else 'negative')}">{exp_bps:+.1f}bp</td>
                <td>{s.get('avg_duration_min', 0.0):.1f}분</td>
            </tr>
            """)
        hourly_table_html = f"""
        <h3>🕒 시간대별(Hourly UTC) 거래 성과</h3>
        <table>
            <thead>
                <tr><th>시간대 (UTC)</th><th>거래수</th><th>승률</th><th>총 수익률</th><th>평균 수익률</th><th>손익비</th><th>기대값</th><th>평균 보유시간</th></tr>
            </thead>
            <tbody>
                {''.join(hour_rows) if hour_rows else '<tr><td colspan="8">시간대 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if hours else ""

        months = data.get("monthly_performance", {})
        month_rows = []
        for m_key, s in months.items():
            tot_p = s.get('total_profit_pct', 0.0)
            avg_p = s.get('avg_profit_pct', 0.0)
            exp_bps = s.get('expectancy_bps', 0.0)
            month_rows.append(f"""
            <tr>
                <td><strong>{m_key}</strong></td>
                <td>{s.get('trades', 0)}</td>
                <td>{s.get('win_rate_pct', 0.0):.1f}%</td>
                <td class="{('positive' if tot_p >= 0 else 'negative')}">{tot_p:+.2f}%</td>
                <td class="{('positive' if avg_p >= 0 else 'negative')}">{avg_p:+.2f}%</td>
                <td class="negative">-{s.get('max_drawdown_pct', 0.0):.2f}%</td>
                <td>{s.get('profit_factor', 0.0):.2f}</td>
                <td class="{('positive' if exp_bps >= 0 else 'negative')}">{exp_bps:+.1f}bp</td>
                <td>{s.get('avg_duration_min', 0.0):.1f}분</td>
            </tr>
            """)
        monthly_table_html = f"""
        <h3>📆 월별(Monthly Calendar) 거래 성과</h3>
        <table>
            <thead>
                <tr><th>월 (Year-Month)</th><th>거래수</th><th>승률</th><th>총 수익률</th><th>평균 수익률</th><th>월간 최대낙폭</th><th>손익비</th><th>기대값</th><th>평균 보유시간</th></tr>
            </thead>
            <tbody>
                {''.join(month_rows) if month_rows else '<tr><td colspan="9">월별 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if months else ""

        exits = data.get("exit_reasons", {})
        exit_rows = []
        for tag, s in exits.items():
            tot_p = s.get('total_profit_pct', 0.0)
            avg_p = s.get('avg_profit_pct', 0.0)
            exit_rows.append(f"""
            <tr>
                <td><code>{tag}</code></td>
                <td>{s.get('trades', 0)}</td>
                <td>{s.get('win_rate_pct', 0.0):.1f}%</td>
                <td class="{('positive' if tot_p >= 0 else 'negative')}">{tot_p:+.2f}%</td>
                <td class="{('positive' if avg_p >= 0 else 'negative')}">{avg_p:+.2f}%</td>
                <td>{s.get('profit_factor', 0.0):.2f}</td>
                <td>{s.get('avg_duration_min', 0.0):.1f}분</td>
            </tr>
            """)
        exit_table_html = f"""
        <h3>🏷️ 청산 사유 및 태그별 성과</h3>
        <table>
            <thead>
                <tr><th>청산 태그</th><th>거래수</th><th>승률</th><th>총 수익률</th><th>평균 수익률</th><th>손익비</th><th>평균 보유시간</th></tr>
            </thead>
            <tbody>
                {''.join(exit_rows) if exit_rows else '<tr><td colspan="7">청산 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if exits else ""

        episodes_info = data.get("drawdown_episodes", {})
        top_eps = episodes_info.get("top_episodes", [])
        ep_rows = []
        for ep in top_eps:
            status_cls = "positive" if ep.get("is_recovered") else "negative"
            status_txt = "✅ 회복완료" if ep.get("is_recovered") else "⏳ 침체진행중"
            ep_rows.append(f"""
            <tr>
                <td><strong>{ep.get('rank')}위</strong></td>
                <td>{ep.get('peak_date')}</td>
                <td>{ep.get('trough_date')}</td>
                <td>{ep.get('recovery_date')}</td>
                <td class="negative">-{ep.get('depth_pct', 0.0):.2f}%</td>
                <td>{ep.get('drawdown_trades')}회</td>
                <td>{ep.get('recovery_trades')}회</td>
                <td>{ep.get('total_trades')}회</td>
                <td class="{status_cls}">{status_txt}</td>
            </tr>
            """)
        dd_episodes_html = f"""
        <h3>📉 주요 낙폭 에피소드(Drawdown Episodes) TOP 5</h3>
        <table>
            <thead>
                <tr><th>순위</th><th>고점 시점</th><th>저점 시점</th><th>회복 시점</th><th>낙폭(Depth)</th><th>하락 거래수</th><th>회복 거래수</th><th>총 침체 거래수</th><th>회복 상태</th></tr>
            </thead>
            <tbody>
                {''.join(ep_rows) if ep_rows else '<tr><td colspan="9">낙폭 에피소드 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if top_eps else ""

        pairs = data.get("pair_performance", {})
        pair_rows = []
        for pair, s in pairs.items():
            tot_p = s.get('total_profit_pct', 0.0)
            avg_p = s.get('avg_profit_pct', 0.0)
            pair_rows.append(f"""
            <tr>
                <td><strong>{pair}</strong></td>
                <td>{s.get('trades', 0)}</td>
                <td>{s.get('win_rate_pct', 0.0):.1f}%</td>
                <td class="{('positive' if tot_p >= 0 else 'negative')}">{tot_p:+.2f}%</td>
                <td class="{('positive' if avg_p >= 0 else 'negative')}">{avg_p:+.2f}%</td>
                <td>{s.get('profit_factor', 0.0):.2f}</td>
                <td>{s.get('avg_duration_min', 0.0):.1f}분</td>
            </tr>
            """)
        pair_table_html = f"""
        <h3>🪙 거래 페어별 성과 비교</h3>
        <table>
            <thead>
                <tr><th>페어</th><th>거래수</th><th>승률</th><th>총 수익률</th><th>평균 수익률</th><th>손익비</th><th>평균 보유시간</th></tr>
            </thead>
            <tbody>
                {''.join(pair_rows) if pair_rows else '<tr><td colspan="7">페어 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if pairs else ""

        rolling_count = data.get("rolling_windows_count", 0)
        rolling_table_html = f"""
        <h3>🔄 롤링 윈도우(Rolling Window) 샤프 및 성과 안정성 ({data.get('rolling_window_size', 30)}거래)</h3>
        <table>
            <thead>
                <tr><th>윈도우 수</th><th>중위 샤프</th><th>샤프 범위</th><th>샤프 변동성(Std)</th><th>수익 일관성</th><th>역성장 윈도우</th><th>롤링 승률</th><th>최악 롤링 MDD</th></tr>
            </thead>
            <tbody>
                <tr>
                    <td>{rolling_count}회</td>
                    <td><strong>{data.get('rolling_sharpe_median', 0.0):.2f}</strong></td>
                    <td>{data.get('rolling_sharpe_min', 0.0):.2f} ~ {data.get('rolling_sharpe_max', 0.0):.2f}</td>
                    <td>{data.get('rolling_sharpe_std', 0.0):.2f}</td>
                    <td class="{'positive' if data.get('consistency_score_pct', 0.0) >= 50 else 'negative'}">{data.get('consistency_score_pct', 0.0):.1f}%</td>
                    <td class="{'negative' if data.get('pct_negative_sharpe_windows', 0.0) > 30 else 'positive'}">{data.get('pct_negative_sharpe_windows', 0.0):.1f}%</td>
                    <td>{data.get('rolling_win_rate_min_pct', 0.0):.1f}% ~ {data.get('rolling_win_rate_max_pct', 0.0):.1f}%</td>
                    <td class="negative">-{data.get('rolling_mdd_worst_pct', 0.0):.2f}%</td>
                </tr>
            </tbody>
        </table>
        """ if rolling_count > 0 else ""

        sens = data.get("slippage_sensitivity", {})
        curve = sens.get("sensitivity_curve", [])
        sens_rows = []
        for row in curve:
            tot_p = row.get('total_return_pct', 0.0)
            exp_b = row.get('expectancy_bps', 0.0)
            sens_rows.append(f"""
            <tr>
                <td><strong>+{row.get('friction_bps', 0):.0f} bps</strong></td>
                <td>{row.get('win_rate_pct', 0.0):.1f}%</td>
                <td class="{('positive' if tot_p >= 0 else 'negative')}">{tot_p:+.2f}%</td>
                <td>{row.get('profit_factor', 0.0):.2f}</td>
                <td class="{('positive' if exp_b >= 0 else 'negative')}">{exp_b:+.1f}bp</td>
                <td class="negative">-{row.get('return_decay_pct', 0.0):.1f}%</td>
            </tr>
            """)
        be_bps = sens.get("breakeven_friction_bps", 0.0)
        rating_txt = sens.get("resilience_rating", "N/A")
        sens_table_html = f"""
        <h3>📉 슬리피지·수수료 마찰 민감도 스트레스 곡선 (Breakeven: {be_bps:.1f} bps / {rating_txt})</h3>
        <table>
            <thead>
                <tr><th>추가 마찰</th><th>승률</th><th>총 수익률</th><th>손익비</th><th>기대값</th><th>수익 감쇄율</th></tr>
            </thead>
            <tbody>
                {''.join(sens_rows) if sens_rows else '<tr><td colspan="6">민감도 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if curve else ""

        conc = data.get("profit_concentration", {})
        conc_table_html = f"""
        <h3>🎯 수익 집중도 및 이상치 의존성 (Outlier Robustness & Concentration)</h3>
        <p><strong>견고성 등급:</strong> <span class="badge {('badge-green' if 'Robust' in conc.get('robustness_rating', '') else ('badge-yellow' if 'Moderate' in conc.get('robustness_rating', '') else 'badge-red'))}">{conc.get('robustness_rating', 'N/A')}</span> | <strong>상위 3개 제외 유지 여부:</strong> {('✅ 흑자 유지' if conc.get('is_profitable_without_top_3') else '❌ 적자 전락')}</p>
        <table>
            <thead>
                <tr><th>지표 항목</th><th>산출값</th><th>평가 및 해석</th></tr>
            </thead>
            <tbody>
                <tr><td><strong>Top 1 거래 수익 비중</strong></td><td>{conc.get('top_1_profit_share_pct', 0.0):.1f}%</td><td>최대 단일 대박 거래 점유율</td></tr>
                <tr><td><strong>Top 3 거래 수익 비중</strong></td><td>{conc.get('top_3_profit_share_pct', 0.0):.1f}%</td><td>상위 3개 극단치 수익 점유율</td></tr>
                <tr><td><strong>Top 10% 거래 수익 비중</strong></td><td>{conc.get('top_10pct_profit_share_pct', 0.0):.1f}%</td><td>상위 10% 거래들의 수익 집중도</td></tr>
                <tr><td><strong>수익 허핀달 지수 (HHI)</strong></td><td>{conc.get('herfindahl_index', 0.0):.1f}</td><td>수익 집중 지수 (&lt; 2500 분산 우수)</td></tr>
                <tr><td><strong>지니 계수 (Gini)</strong></td><td>{conc.get('gini_coefficient', 0.0):.3f}</td><td>수익 불평등도 (0.0: 균등 ~ 1.0: 독점)</td></tr>
                <tr><td><strong>상위 3개 제외 순수익률 (Trimmed)</strong></td><td class="{('positive' if conc.get('profit_without_top_3_pct', 0.0) >= 0 else 'negative')}">{conc.get('profit_without_top_3_pct', 0.0):+.2f}%</td><td>상위 3개 제외 시 잔여 순수익률</td></tr>
                <tr><td><strong>상위 3개 제외 손익비 (Trimmed PF)</strong></td><td>{conc.get('pf_without_top_3', 0.0):.2f}</td><td>상위 3개 제외 시 기초 손익비</td></tr>
                <tr><td><strong>상위 3개 제거 수익 감쇄율</strong></td><td class="negative">-{conc.get('trimmed_profit_decay_pct', 0.0):.1f}%</td><td>극단치 제거 시 수익 감소폭</td></tr>
            </tbody>
        </table>
        """ if conc and conc.get("robustness_rating") != "N/A" else ""

        conc_exp = data.get("concurrency_analysis", {})
        concurrency_table_html = f"""
        <h3>🔀 동시 보유 포지션(Concurrency) 및 자본 활용도</h3>
        <p><strong>자본 효율성 등급:</strong> <span class="badge {('badge-green' if 'High Capital' in conc_exp.get('capital_efficiency_rating', '') else ('badge-yellow' if 'Balanced' in conc_exp.get('capital_efficiency_rating', '') else 'badge-red'))}">{conc_exp.get('capital_efficiency_rating', 'N/A')}</span> | <strong>최대 동시 슬롯:</strong> {conc_exp.get('peak_concurrent_trades', 0)}개 | <strong>시간가중 평균:</strong> {conc_exp.get('avg_concurrent_trades', 0.0):.1f}개 | <strong>유휴 시간:</strong> {conc_exp.get('idle_time_pct', 0.0):.1f}%</p>
        <table>
            <thead>
                <tr><th>동시 진입 밀도</th><th>거래수</th><th>승률</th><th>총 수익률</th><th>손익비</th><th>기대값</th></tr>
            </thead>
            <tbody>
                {''.join(f'''<tr>
                    <td><strong>{slot_name}</strong></td>
                    <td>{s.get("trades", 0)}회</td>
                    <td>{s.get("win_rate_pct", 0.0):.1f}%</td>
                    <td class="{('positive' if s.get('total_profit_pct', 0.0) >= 0 else 'negative')}">{s.get('total_profit_pct', 0.0):+.2f}%</td>
                    <td>{s.get("profit_factor", 0.0):.2f}</td>
                    <td class="{('positive' if s.get('expectancy_bps', 0.0) >= 0 else 'negative')}">{s.get('expectancy_bps', 0.0):+.1f}bp</td>
                </tr>''' for slot_name, s in conc_exp.get("slot_tier_performance", {}).items()) if conc_exp.get("slot_tier_performance") else '<tr><td colspan="6">동시성 데이터 없음</td></tr>'}
            </tbody>
        </table>
        """ if conc_exp and conc_exp.get("capital_efficiency_rating") != "N/A" else ""

        mae_mfe = data.get("mae_mfe_analysis", {})
        mae_mfe_table_html = f"""
        <h3>🎯 MAE / MFE 진입 우위 및 청산 효율성 (Excursion & Edge)</h3>
        <p><strong>우위 등급:</strong> <span class="badge {('badge-green' if 'High Edge' in mae_mfe.get('edge_rating', '') else ('badge-primary' if 'Solid' in mae_mfe.get('edge_rating', '') else ('badge-yellow' if 'Marginal' in mae_mfe.get('edge_rating', '') else 'badge-red')))}">{mae_mfe.get('edge_rating', 'N/A')}</span> | <strong>우위 지수 (Edge Ratio):</strong> {mae_mfe.get('edge_ratio', 0.0):.2f} | <strong>승리 거래 청산 효율성:</strong> {mae_mfe.get('avg_win_capture_pct', 0.0):.1f}% | <strong>권장 스탑로스:</strong> -{mae_mfe.get('optimal_sl_suggestion_pct', 0.0):.2f}%</p>
        <table>
            <thead>
                <tr><th>지표 항목</th><th>전체 거래</th><th>승리 거래 (Wins)</th><th>패배 거래 (Losses)</th></tr>
            </thead>
            <tbody>
                <tr><td><strong>평균 최대 역행 진폭 (Avg MAE)</strong></td><td class="negative">{mae_mfe.get('avg_mae_pct', 0.0):+.2f}%</td><td class="negative">{mae_mfe.get('avg_win_mae_pct', 0.0):+.2f}%</td><td class="negative">{mae_mfe.get('avg_loss_mae_pct', 0.0):+.2f}%</td></tr>
                <tr><td><strong>평균 최대 순행 진폭 (Avg MFE)</strong></td><td class="positive">{mae_mfe.get('avg_mfe_pct', 0.0):+.2f}%</td><td class="positive">{mae_mfe.get('avg_win_mfe_pct', 0.0):+.2f}%</td><td class="positive">{mae_mfe.get('avg_loss_mfe_pct', 0.0):+.2f}%</td></tr>
                <tr><td><strong>수익 반납 후 손절 (Wasted Winners)</strong></td><td>{mae_mfe.get('wasted_winners_count', 0)}회 ({mae_mfe.get('wasted_winners_pct', 0.0):.1f}%)</td><td>-</td><td class="negative">손실 중 +1.0% 이상 반납분</td></tr>
            </tbody>
        </table>
        """ if mae_mfe and mae_mfe.get("edge_rating") != "N/A" else ""

        sections.append(f"""
        <section class="strategy-section">
            <h2>📈 전략: <span class="strategy-title">{name}</span></h2>
            {cards_html}
            {dir_table_html}
            {dow_table_html}
            {tier_table_html}
            {stake_table_html}
            {hourly_table_html}
            {monthly_table_html}
            {rolling_table_html}
            {sens_table_html}
            {conc_table_html}
            {concurrency_table_html}
            {mae_mfe_table_html}
            {dd_episodes_html}
            {exit_table_html}
            {pair_table_html}
        </section>
        """)

    full_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Freqtrade Quantitative Backtest Report</title>
    <style>
        :root {{
            --bg: #0d1117;
            --surface: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --heading: #f0f6fc;
            --primary: #58a6ff;
            --green: #3fb950;
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
        header {{ margin-bottom: 32px; border-bottom: 1px solid var(--border); padding-bottom: 16px; }}
        h1 {{ color: var(--heading); font-size: 26px; display: flex; align-items: center; gap: 8px; }}
        h2 {{ color: var(--heading); font-size: 20px; margin: 24px 0 16px; }}
        h3 {{ color: var(--heading); font-size: 16px; margin: 20px 0 10px; }}
        .strategy-title {{ color: var(--primary); }}
        .strategy-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 24px; margin-bottom: 32px; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 24px; }}
        .metric-card {{ background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 14px; }}
        .metric-label {{ font-size: 12px; color: #8b949e; margin-bottom: 6px; }}
        .metric-value {{ font-size: 18px; font-weight: 600; color: var(--heading); }}
        .positive {{ color: var(--green) !important; }}
        .negative {{ color: var(--red) !important; }}
        .badge {{ display: inline-block; padding: 2px 6px; font-size: 11px; font-weight: 500; border-radius: 10px; margin-left: 6px; }}
        .badge-primary {{ background: rgba(88, 166, 255, 0.15); color: var(--primary); border: 1px solid rgba(88, 166, 255, 0.3); }}
        .badge-success {{ background: rgba(63, 185, 80, 0.15); color: var(--green); border: 1px solid rgba(63, 185, 80, 0.3); }}
        .badge-warning {{ background: rgba(210, 153, 34, 0.15); color: #d29922; border: 1px solid rgba(210, 153, 34, 0.3); }}
        .badge-danger {{ background: rgba(248, 81, 73, 0.15); color: var(--red); border: 1px solid rgba(248, 81, 73, 0.3); }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 8px; margin-bottom: 20px; font-size: 13px; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ background: var(--bg); color: #8b949e; font-weight: 600; }}
        tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}
        code {{ background: rgba(110, 118, 129, 0.2); padding: 2px 6px; border-radius: 4px; font-size: 12px; color: var(--primary); }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 Freqtrade Quantitative Backtest Report</h1>
            <p style="color: #8b949e; font-size: 13px; margin-top: 4px;">Institutional Performance & Downside Risk Analytics</p>
        </header>
        {''.join(sections)}
    </div>
</body>
</html>
"""
    return full_html


def find_latest_backtest_file(directory: Path | str | None = None) -> Path:
    """Find the most recent backtest result file (.zip or .json) in the specified directory.

    Checks:
    1. .last_result.json in directory if present (reads 'latest_backtest' attribute)
    2. Most recently modified backtest-result-*.zip or backtest-result-*.json
    3. Any *.zip or *.json (excluding .meta.json, _config.json, .last_result.json, quant-analysis*)
    """
    if directory is None:
        repo_root = Path(__file__).resolve().parents[1]
        default_dir = repo_root / "user_data" / "backtest_results"
        target_dir = default_dir if default_dir.is_dir() else Path.cwd()
    else:
        target_dir = Path(directory)

    if not target_dir.is_dir():
        raise FileNotFoundError(f"Target directory for backtest discovery does not exist: {target_dir}")

    # Check .last_result.json
    last_result_meta = target_dir / ".last_result.json"
    if last_result_meta.is_file():
        try:
            with open(last_result_meta, "r", encoding="utf-8") as f:
                meta = json.load(f)
            latest_filename = meta.get("latest_backtest")
            if latest_filename:
                candidate = target_dir / latest_filename
                if candidate.is_file():
                    return candidate
        except Exception:
            pass

    excluded_suffixes = {".meta.json", ".csv", ".html", ".md", ".feather"}
    candidates: list[Path] = []

    # First search target_dir directly, and immediate subdirectories
    search_paths = [target_dir]
    for sub in target_dir.iterdir():
        if sub.is_dir() and not sub.name.startswith("."):
            search_paths.append(sub)

    for p in search_paths:
        for f in p.glob("*"):
            if not f.is_file():
                continue
            name_lower = f.name.lower()
            if any(name_lower.endswith(ex) for ex in excluded_suffixes):
                continue
            if name_lower.startswith(".last_result") or name_lower.endswith("_config.json") or "quant-analysis" in name_lower:
                continue
            if f.suffix.lower() in {".zip", ".json"}:
                candidates.append(f)

    if not candidates:
        raise FileNotFoundError(f"No backtest result (.zip or .json) found in {target_dir}")

    def sort_key(p: Path) -> tuple[int, float]:
        is_primary = 1 if "backtest-result" in p.name.lower() else 0
        try:
            mtime = p.stat().st_mtime
        except Exception:
            mtime = 0.0
        return (is_primary, mtime)

    candidates.sort(key=sort_key, reverse=True)
    return candidates[0]


def load_backtest_data(
    file_or_dir_path: Path | str | None = None,
    latest: bool = False,
) -> tuple[dict[str, Any], Path]:
    """Load and parse Freqtrade backtest data from a .json file, a .zip archive, or directory.

    Returns (parsed_data_dict, resolved_file_path).
    """
    if file_or_dir_path is None or latest:
        resolved = find_latest_backtest_file(file_or_dir_path if file_or_dir_path else None)
    else:
        p = Path(file_or_dir_path)
        if p.is_dir():
            resolved = find_latest_backtest_file(p)
        elif p.name.lower() == ".last_result.json":
            resolved = find_latest_backtest_file(p.parent)
        elif not p.exists():
            raise FileNotFoundError(f"Backtest result file not found: {p}")
        else:
            resolved = p

    if resolved.suffix.lower() == ".zip":
        with zipfile.ZipFile(resolved, "r") as zf:
            namelist = zf.namelist()
            target_name = None
            expected_json_name = resolved.stem + ".json"
            if expected_json_name in namelist:
                target_name = expected_json_name
            else:
                for name in namelist:
                    n_lower = name.lower()
                    if n_lower.endswith(".json") and not n_lower.endswith("_config.json") and not n_lower.endswith(".meta.json"):
                        target_name = name
                        break
            if not target_name:
                raise ValueError(f"No valid backtest result JSON found inside archive: {resolved}")
            raw_bytes = zf.read(target_name)
            data = json.loads(raw_bytes.decode("utf-8"))
    else:
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)

    return data, resolved


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Freqtrade backtest results for Ulcer Index, Drawdown & institutional metrics"
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=str,
        default=None,
        help="Path to backtest-result.json, .zip archive, or results directory (optional if --latest is used)",
    )
    parser.add_argument(
        "--latest",
        "-l",
        action="store_true",
        help="Automatically find and analyze the most recent backtest result (.zip or .json) in user_data/backtest_results",
    )
    parser.add_argument("--output", "-o", type=str, default=None, help="Optional output Markdown path")
    parser.add_argument("--json", "-j", type=str, default=None, help="Optional output JSON path for programmatic consumption")
    parser.add_argument("--csv", "-c", type=str, default=None, help="Optional output CSV path for tabular consumption")
    parser.add_argument("--html", "-H", type=str, default=None, help="Optional output HTML path for standalone visual report")
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
    parser.add_argument(
        "--monte-carlo",
        "-mc",
        action="store_true",
        help="Run Monte Carlo trade permutation simulation to test sequence risk and worst-case drawdowns",
    )
    parser.add_argument(
        "--mc-iterations",
        type=int,
        default=1000,
        help="Number of Monte Carlo reshuffle iterations (default: 1000)",
    )
    parser.add_argument(
        "--mc-threshold",
        type=float,
        default=20.0,
        help="Drawdown ruin threshold percentage to evaluate exceedance probability (default: 20.0)",
    )
    args = parser.parse_args()

    data, file_path = load_backtest_data(args.file, latest=args.latest)
    print(f"[*] Analyzing backtest results from: {file_path}")

    results = parse_freqtrade_backtest_json(
        data,
        sort_by=args.sort_by,
        min_trades=args.min_trades,
        monte_carlo=args.monte_carlo,
        mc_iterations=args.mc_iterations,
        mc_threshold_pct=args.mc_threshold,
    )
    md_content = generate_markdown_report(results)

    if args.json:
        json_path = Path(args.json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"[+] Quant analysis JSON exported to: {json_path}")

    if args.csv:
        csv_content = export_quant_analysis_csv(results)
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_content)
        print(f"[+] Quant analysis CSV exported to: {csv_path}")

    if args.html:
        html_content = generate_html_report(results)
        html_path = Path(args.html)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"[+] Quant analysis HTML exported to: {html_path}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"[+] Quant analysis report exported to: {out_path}")
    elif not args.json and not args.csv and not args.html:
        try:
            print(md_content)
        except UnicodeEncodeError:
            print(md_content.encode("ascii", "replace").decode("ascii"))


if __name__ == "__main__":
    main()

