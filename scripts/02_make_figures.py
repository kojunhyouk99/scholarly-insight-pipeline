#!/usr/bin/env python3
"""Generate figures that summarise arXiv category trends."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd

from analysis_utils import (
    TrendData,
    compute_category_statistics,
    compute_overall_summary,
    export_category_stats,
    export_summary,
    format_summary_text,
    load_monthly,
    to_monthly_matrix,
)


def _configure_fonts() -> None:
    desired = ("AppleGothic", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR")
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in desired:
        if name in available:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def _save_figure(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _plot_total(trend: TrendData, out_dir: Path) -> None:
    total = trend.totals
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(total.index, total.values, label="Monthly uploads", color="#0B6E4F", linewidth=1.4)
    rolling6 = total.rolling(window=6).mean()
    rolling12 = total.rolling(window=12).mean()
    ax.plot(total.index, rolling6, label="6-month rolling avg", color="#1F77B4", linewidth=1.2)
    ax.plot(total.index, rolling12, label="12-month rolling avg", color="#FF7F0E", linewidth=1.2)
    ax.set_title("Monthly arXiv uploads with rolling averages")
    ax.set_xlabel("Month")
    ax.set_ylabel("Papers")
    ax.legend()
    _save_figure(fig, out_dir / "01_monthly_total.png")


def _plot_growth(category_stats: pd.DataFrame, out_dir: Path, top_n: int) -> None:
    growth = category_stats.sort_values("yoy_pct", ascending=False).head(top_n)
    growth = growth[growth["yoy_pct"].notna()]
    if growth.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.barh(
        growth["main_cat"][::-1],
        growth["yoy_pct"][::-1],
        color="#1F77B4",
    )
    ax.set_title(f"Fastest growing categories (YoY %, Top-{len(growth)})")
    ax.set_xlabel("Year-over-year growth (%)")
    _save_figure(fig, out_dir / "02_top_growth.png")


def _plot_share(category_stats: pd.DataFrame, out_dir: Path, top_n: int) -> None:
    share = category_stats.sort_values("last12_share_pct", ascending=False).head(top_n)
    if share.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(share["main_cat"][::-1], share["last12_total"][::-1], color="#D62728")
    ax.set_title(f"Top categories by upload volume (Top-{len(share)})")
    ax.set_xlabel("Uploads in last 12 months")
    _save_figure(fig, out_dir / "03_top_share.png")


def _plot_heatmap(trend: TrendData, out_dir: Path, months: int, top_n: int) -> None:
    window = trend.matrix.tail(months)
    totals = window.sum().sort_values(ascending=False).head(top_n)
    if totals.empty:
        return
    subset = window[totals.index].T
    fig, ax = plt.subplots(figsize=(12, max(6, top_n * 0.35)))
    im = ax.imshow(subset, aspect="auto", cmap="viridis")
    ax.set_yticks(np.arange(len(subset.index)))
    ax.set_yticklabels(subset.index)
    ax.set_xticks(np.arange(len(subset.columns)))
    ax.set_xticklabels([ts.strftime("%Y-%m") for ts in subset.columns], rotation=45, ha="right", fontsize=8)
    ax.set_title(f"Heatmap: Top {len(subset.index)} categories over last {len(subset.columns)} months")
    ax.set_xlabel("Month")
    ax.set_ylabel("Category")
    fig.colorbar(im, ax=ax, label="Uploads")
    _save_figure(fig, out_dir / "04_category_heatmap.png")


def _plot_growth_vs_volume(category_stats: pd.DataFrame, out_dir: Path, label_top: int) -> None:
    data = category_stats[category_stats["last12_total"] > 0]
    if data.empty:
        return
    fig, ax = plt.subplots(figsize=(9, 6))
    scatter = ax.scatter(
        data["last12_total"],
        data["yoy_pct"],
        c=data["momentum_slope"],
        cmap="coolwarm",
        alpha=0.7,
    )
    ax.set_xscale("log")
    ax.set_xlabel("Uploads in last 12 months (log scale)")
    ax.set_ylabel("YoY growth (%)")
    ax.set_title("Growth vs. volume (color = momentum slope)")
    fig.colorbar(scatter, ax=ax, label="Momentum (slope)")

    top_labels = data.sort_values("yoy_pct", ascending=False).head(label_top)
    for _, row in top_labels.iterrows():
        ax.annotate(
            row["main_cat"],
            (row["last12_total"], row["yoy_pct"]),
            textcoords="offset points",
            xytext=(4, 4),
            fontsize=8,
        )

    _save_figure(fig, out_dir / "05_growth_vs_volume.png")


def _plot_volatility(category_stats: pd.DataFrame, out_dir: Path, top_n: int) -> None:
    data = category_stats.sort_values("volatility_index", ascending=False).head(top_n)
    if data.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(data["main_cat"][::-1], data["volatility_index"][::-1], color="#9467BD")
    ax.set_title(f"Most volatile categories (Top-{len(data)})")
    ax.set_xlabel("Volatility index (std dev / mean)")
    _save_figure(fig, out_dir / "06_volatility.png")


def _main(args: argparse.Namespace) -> int:
    csv_path = Path(args.data)
    out_dir = Path(args.figures)
    if not csv_path.exists():
        raise SystemExit(f"Missing aggregate CSV: {csv_path}")

    df = load_monthly(csv_path)
    trend = to_monthly_matrix(df)
    category_stats = compute_category_statistics(trend, recent_months=12, slope_window=args.momentum_window)
    summary = compute_overall_summary(trend, category_stats, recent_months=12)

    _configure_fonts()
    _plot_total(trend, out_dir)
    _plot_growth(category_stats, out_dir, top_n=args.top_growth)
    _plot_share(category_stats, out_dir, top_n=args.top_share)
    _plot_heatmap(trend, out_dir, months=args.heatmap_months, top_n=args.heatmap_top)
    _plot_growth_vs_volume(category_stats, out_dir, label_top=args.scatter_labels)
    _plot_volatility(category_stats, out_dir, top_n=args.top_volatility)

    out_dir.mkdir(parents=True, exist_ok=True)
    pivot_path = csv_path.parent / "arxiv_last12_pivot.csv"
    last12_matrix = trend.matrix.tail(12)
    pivot = last12_matrix.T.sort_values(by=last12_matrix.index[-1], ascending=False)
    pivot.to_csv(pivot_path)
    export_category_stats(category_stats, csv_path.parent / "arxiv_category_stats.csv")
    export_summary(summary, csv_path.parent / "arxiv_summary.json")
    if args.report:
        format_summary_text(summary, category_stats, Path(args.report))

    print(f"Saved figures to {out_dir.resolve()}")
    print(f"Exported category stats → {csv_path.parent / 'arxiv_category_stats.csv'}")
    print(f"Exported summary JSON → {csv_path.parent / 'arxiv_summary.json'}")
    if args.report:
        print(f"Wrote textual summary → {args.report}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create figures from the arXiv aggregate CSV.")
    parser.add_argument("--data", default="data/arxiv_monthly.csv", help="Aggregate CSV path")
    parser.add_argument("--figures", default="figures", help="Output directory for PNG files")
    parser.add_argument(
        "--top-growth", type=int, default=15, help="How many categories to show in the growth chart"
    )
    parser.add_argument(
        "--top-share", type=int, default=10, help="How many categories to show in the share chart"
    )
    parser.add_argument(
        "--heatmap-months", type=int, default=24, help="Number of trailing months to display in the heatmap"
    )
    parser.add_argument(
        "--heatmap-top", type=int, default=20, help="Number of categories to include in the heatmap"
    )
    parser.add_argument(
        "--scatter-labels", type=int, default=12, help="Number of labels to display on the growth vs volume scatter"
    )
    parser.add_argument(
        "--top-volatility", type=int, default=10, help="How many categories to show in the volatility chart"
    )
    parser.add_argument(
        "--momentum-window", type=int, default=24, help="Window size (months) when computing momentum slopes"
    )
    parser.add_argument(
        "--report", default="reports/trend_summary.txt", help="Path for the textual summary report (set blank to skip)"
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(_main(args))


if __name__ == "__main__":
    main()
