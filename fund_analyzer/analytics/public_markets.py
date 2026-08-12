from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class PublicMetrics:
    values: dict[str, float | None] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _clean(values: pd.Series) -> pd.Series:
    result = values.astype(float).replace([np.inf, -np.inf], np.nan).dropna().sort_index()
    return result[~result.index.duplicated(keep="last")]


def growth_of_amount(values: pd.Series, amount: float = 100_000) -> pd.Series:
    values = _clean(values)
    if values.empty or values.iloc[0] <= 0:
        return pd.Series(dtype=float)
    return amount * values / values.iloc[0]


def calculate_max_drawdown(values: pd.Series) -> float | None:
    values = _clean(values)
    if values.empty:
        return None
    return float((values / values.cummax() - 1).min())


def _period_return(values: pd.Series, years: int) -> float | None:
    end = values.index.max()
    target = end - pd.DateOffset(years=years)
    eligible = values[values.index <= target]
    if eligible.empty:
        return None
    start_value = eligible.iloc[-1]
    elapsed = (end - eligible.index[-1]).days / 365.2425
    if elapsed < years * 0.95 or start_value <= 0:
        return None
    return float((values.iloc[-1] / start_value) ** (1 / elapsed) - 1)


def calculate_public_metrics(values: pd.Series, benchmark: pd.Series | None, risk_free_rate: float | None) -> PublicMetrics:
    values = _clean(values)
    warnings: list[str] = []
    cagr_1y = _period_return(values, 1) if len(values) >= 12 else None
    if cagr_1y is None:
        warnings.append("insufficient 1-year coverage")
    returns = values.pct_change().dropna()
    daily_like = len(returns) >= 200
    volatility = float(returns.std(ddof=1) * np.sqrt(252)) if daily_like else None
    sharpe = None
    sortino = None
    alpha = None
    if daily_like and risk_free_rate is not None and volatility and volatility > 0:
        daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
        excess = returns - daily_rf
        sharpe = float(excess.mean() / returns.std(ddof=1) * np.sqrt(252))
        downside = returns[returns < 0].std(ddof=1)
        sortino = float(excess.mean() / downside * np.sqrt(252)) if downside and not np.isnan(downside) else None
    if benchmark is not None:
        aligned = pd.concat([values.pct_change(), _clean(benchmark).pct_change()], axis=1, join="inner").dropna()
        if len(aligned) >= 200:
            covariance = np.cov(aligned.iloc[:, 0], aligned.iloc[:, 1], ddof=1)[0, 1]
            variance = aligned.iloc[:, 1].var(ddof=1)
            beta = covariance / variance if variance else np.nan
            rf_daily = (1 + (risk_free_rate or 0)) ** (1 / 252) - 1
            alpha = float((aligned.iloc[:, 0].mean() - rf_daily - beta * (aligned.iloc[:, 1].mean() - rf_daily)) * 252)
    return PublicMetrics(values={
        "cagr_1y": cagr_1y,
        "cagr_3y": _period_return(values, 3),
        "cagr_5y": _period_return(values, 5),
        "volatility": volatility,
        "max_drawdown": calculate_max_drawdown(values),
        "sharpe": sharpe,
        "sortino": sortino,
        "alpha": alpha,
    }, warnings=warnings)

