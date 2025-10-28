"""Shared utilities for computing arXiv trend statistics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd


MONTHS_IN_YEAR = 12


@dataclass(frozen=True)
class TrendData:
    matrix: pd.DataFrame  # index: year_month (Timestamp at month start), columns: main_cat
    totals: pd.Series     # monthly totals across all categories


def load_monthly(path: Path | str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["year_month"])
    if df.empty:
        raise SystemExit("Aggregate CSV is empty. Run 01_stream_aggregate.py first.")
    return df


def to_monthly_matrix(df: pd.DataFrame) -> TrendData:
    pivot = (
        df.pivot_table(index="year_month", columns="main_cat", values="count", aggfunc="sum")
        .sort_index()
        .fillna(0)
    )
    full_index = pd.period_range(pivot.index.min(), pivot.index.max(), freq="M").to_timestamp()
    pivot = pivot.reindex(full_index, fill_value=0)
    totals = pivot.sum(axis=1)
    return TrendData(matrix=pivot, totals=totals)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.replace(0, np.nan)
    ratio = (numerator - denominator) / denom
    return ratio.replace([np.inf, -np.inf], np.nan)


def _polyfit_slope(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    if arr.size < 2 or np.allclose(arr, 0):
        return 0.0
    x = np.arange(arr.size, dtype=float)
    slope, _ = np.polyfit(x, arr, 1)
    return float(slope)


def compute_category_statistics(
    data: TrendData,
    recent_months: int = 12,
    slope_window: int = 24,
) -> pd.DataFrame:
    matrix = data.matrix

    last = matrix.tail(recent_months)
    prev = matrix.iloc[-recent_months * 2 : -recent_months] if len(matrix) >= recent_months * 2 else None

    last_sum = last.sum()
    prev_sum = prev.sum() if prev is not None else pd.Series(0, index=matrix.columns)
    yoy_pct = _safe_ratio(last_sum, prev_sum) * 100
    abs_change = last_sum - prev_sum
    share_pct = (last_sum / last_sum.sum() * 100) if last_sum.sum() > 0 else pd.Series(0, index=matrix.columns)
    volatility = last.std(ddof=0)
    avg_recent = last.mean()

    window = matrix.tail(slope_window) if len(matrix) >= slope_window else matrix
    slopes = {
        cat: _polyfit_slope(window[cat].values)
        for cat in matrix.columns
    }

    stats = pd.DataFrame(
        {
            "main_cat": matrix.columns,
            "last12_total": last_sum.values.astype(int),
            "prev12_total": prev_sum.values.astype(int),
            "yoy_pct": yoy_pct.fillna(0).values,
            "absolute_change": abs_change.values.astype(int),
            "last12_share_pct": share_pct.fillna(0).values,
            "last12_avg_per_month": avg_recent.values,
            "last12_volatility": volatility.values,
            "momentum_slope": pd.Series(slopes).reindex(matrix.columns).fillna(0).values,
        }
    )

    stats["volatility_index"] = stats["last12_volatility"] / stats["last12_avg_per_month"].replace(0, np.nan)
    stats["volatility_index"] = stats["volatility_index"].replace([np.inf, -np.inf], np.nan).fillna(0)
    return stats


def _seasonality_metrics(totals: pd.Series) -> Dict[str, float | str]:
    by_month = totals.groupby(totals.index.month).mean()
    strongest_month = int(by_month.idxmax()) if not by_month.empty else None
    weakest_month = int(by_month.idxmin()) if not by_month.empty else None
    seasonality_strength = float(by_month.std(ddof=0) / by_month.mean()) if by_month.mean() else 0.0
    return {
        "seasonality_strength": seasonality_strength,
        "strongest_month": strongest_month,
        "weakest_month": weakest_month,
    }


def compute_overall_summary(
    data: TrendData,
    category_stats: pd.DataFrame,
    recent_months: int = 12,
) -> Dict[str, object]:
    totals = data.totals
    latest_month = totals.index.max()
    last = totals.tail(recent_months)
    prev = totals.iloc[-recent_months * 2 : -recent_months] if len(totals) >= recent_months * 2 else pd.Series(dtype=float)

    last_sum = float(last.sum())
    prev_sum = float(prev.sum()) if not prev.empty else 0.0
    yoy_pct = ((last_sum - prev_sum) / prev_sum * 100) if prev_sum else None
    yoy_change = last_sum - prev_sum if prev_sum else None

    rolling_window = 6
    rolling_avg = last.rolling(window=rolling_window).mean().iloc[-1] if len(last) >= rolling_window else float(last.mean())
    rolling12_avg = last.mean()
    slope_window = totals.tail(36) if len(totals) >= 36 else totals
    trend_slope = _polyfit_slope(slope_window.values)
    trend_slope_pct = trend_slope / slope_window.mean() * 100 if slope_window.mean() else 0.0

    cagr = None
    if len(totals) >= MONTHS_IN_YEAR * 6:  # need at least 6 years for 5-year CAGR window
        recent_year = totals.tail(MONTHS_IN_YEAR).sum()
        old_period = totals.iloc[-(MONTHS_IN_YEAR * 6) : -(MONTHS_IN_YEAR * 5)].sum()
        if old_period > 0:
            years = 5
            cagr = (recent_year / old_period) ** (1 / years) - 1

    top_growth = (
        category_stats[category_stats["yoy_pct"].notna()]
        .sort_values("yoy_pct", ascending=False)
        .head(5)
        .to_dict(orient="records")
    )
    top_decline = (
        category_stats[category_stats["yoy_pct"].notna()]
        .sort_values("yoy_pct", ascending=True)
        .head(5)
        .to_dict(orient="records")
    )
    top_volume = category_stats.sort_values("last12_total", ascending=False).head(5).to_dict(orient="records")
    top_momentum = category_stats.sort_values("momentum_slope", ascending=False).head(5).to_dict(orient="records")
    most_volatile = (
        category_stats.sort_values("volatility_index", ascending=False)
        .head(5)
        .to_dict(orient="records")
    )

    seasonality = _seasonality_metrics(totals)

    return {
        "latest_month": latest_month.strftime("%Y-%m"),
        "total_last12": last_sum,
        "total_prev12": prev_sum,
        "total_yoy_pct": yoy_pct,
        "total_yoy_change": yoy_change,
        "rolling6_avg": float(rolling_avg),
        "rolling12_avg": float(rolling12_avg),
        "trend_slope": trend_slope,
        "trend_slope_pct": trend_slope_pct,
        "cagr_5yr": cagr,
        "seasonality": seasonality,
        "top_growth": top_growth,
        "top_decline": top_decline,
        "top_volume": top_volume,
        "top_momentum": top_momentum,
        "most_volatile": most_volatile,
    }


def export_category_stats(stats: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stats.to_csv(path, index=False)


def export_summary(summary: Dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    def _default(obj):
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.strftime("%Y-%m-%d")
        return str(obj)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=_default)


def format_summary_text(summary: Dict[str, object], category_stats: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def _format_top(key: str) -> List[str]:
        records = summary.get(key, [])
        lines = []
        for rec in records:
            cat = rec.get("main_cat", "N/A")
            yoy = rec.get("yoy_pct")
            abs_change = rec.get("absolute_change")
            share = rec.get("last12_share_pct")
            components = [f"{cat}"]
            if yoy is not None:
                components.append(f"YoY {yoy:+.1f}%")
            if abs_change is not None:
                components.append(f"Δ {abs_change:+,}")
            if share is not None:
                components.append(f"share {share:.1f}%")
            lines.append(" - " + " | ".join(components))
        return lines

    total_last12 = summary.get("total_last12", 0)
    total_prev12 = summary.get("total_prev12")
    yoy_pct = summary.get("total_yoy_pct")
    cagr = summary.get("cagr_5yr")

    lines = [
        "ArXiv Trend Summary",
        "===================",
        f"Latest month: {summary.get('latest_month', 'N/A')}",
        f"12-month uploads: {total_last12:,.0f}",
    ]
    if total_prev12:
        lines.append(f"Prior 12-month uploads: {total_prev12:,.0f}")
    if yoy_pct is not None:
        lines.append(f"Year-over-year growth: {yoy_pct:+.2f}%")
    if summary.get("total_yoy_change") is not None:
        lines.append(f"Absolute change (YoY): {summary['total_yoy_change']:+,.0f}")
    lines.append(f"Rolling 6-month avg: {summary.get('rolling6_avg', 0):,.1f}")
    lines.append(f"Rolling 12-month avg: {summary.get('rolling12_avg', 0):,.1f}")
    lines.append(f"Trend slope (last 36 months): {summary.get('trend_slope', 0):+.2f} papers/month")
    lines.append(f"Trend slope (% of mean): {summary.get('trend_slope_pct', 0):+.2f}%")
    if cagr is not None:
        lines.append(f"5-year CAGR: {cagr*100:+.2f}%")

    seasonality = summary.get("seasonality", {})
    if seasonality:
        month_names = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        strongest = seasonality.get("strongest_month")
        weakest = seasonality.get("weakest_month")
        strength = seasonality.get("seasonality_strength", 0) * 100
        if strongest:
            lines.append(f"Seasonal peak month: {month_names[strongest-1]}")
        if weakest:
            lines.append(f"Seasonal low month: {month_names[weakest-1]}")
        lines.append(f"Seasonality strength: {strength:.2f}%")

    sections = [
        ("Top Growth Categories", "top_growth"),
        ("Top Declining Categories", "top_decline"),
        ("Largest Categories (by volume)", "top_volume"),
        ("Strongest Momentum (slope)", "top_momentum"),
        ("Most Volatile Categories", "most_volatile"),
    ]
    for title, key in sections:
        lines.append("")
        lines.append(title)
        lines.append("-" * len(title))
        entries = _format_top(key)
        if entries:
            lines.extend(entries)
        else:
            lines.append(" - None")

    with path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
