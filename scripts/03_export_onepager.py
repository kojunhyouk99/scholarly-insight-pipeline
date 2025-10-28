#!/usr/bin/env python3
"""Assemble a one-page PDF summary using the generated figures."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import textwrap

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from analysis_utils import (
    compute_category_statistics,
    compute_overall_summary,
    load_monthly,
    to_monthly_matrix,
)

@dataclass(frozen=True)
class Assets:
    data: Path
    total_fig: Path
    growth_fig: Path
    share_fig: Path
    heatmap_fig: Path
    scatter_fig: Path
    volatility_fig: Path
    summary_json: Path
    category_stats: Path
    output_pdf: Path


def _load_summary(assets: Assets) -> tuple[dict, pd.DataFrame]:
    summary = {}
    stats_df = None

    if assets.summary_json.exists():
        with assets.summary_json.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
    if assets.category_stats.exists():
        stats_df = pd.read_csv(assets.category_stats)

    if summary and stats_df is not None:
        return summary, stats_df

    # Fallback: recompute from CSV
    df = load_monthly(assets.data)
    trend = to_monthly_matrix(df)
    stats_df = compute_category_statistics(trend, recent_months=12, slope_window=24)
    summary = compute_overall_summary(trend, stats_df, recent_months=12)
    return summary, stats_df


def _format_number(value, fmt: str = "{:,.0f}") -> str:
    if value is None:
        return "N/A"
    return fmt.format(value)


def _build_highlights(summary: dict) -> list[str]:
    latest = summary.get("latest_month", "N/A")
    total = _format_number(summary.get("total_last12"))
    prev = summary.get("total_prev12")
    yoy_pct = summary.get("total_yoy_pct")
    yoy_change = summary.get("total_yoy_change")
    rolling6 = _format_number(summary.get("rolling6_avg"), "{:,.0f}")
    rolling12 = _format_number(summary.get("rolling12_avg"), "{:,.0f}")
    slope = summary.get("trend_slope", 0)
    slope_pct = summary.get("trend_slope_pct", 0)
    cagr = summary.get("cagr_5yr")
    seasonality = summary.get("seasonality", {}) or {}

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    peak = seasonality.get("strongest_month")
    low = seasonality.get("weakest_month")
    peak_str = month_names[int(peak) - 1] if peak else "N/A"
    low_str = month_names[int(low) - 1] if low else "N/A"

    highlights = [
        f"Latest month: {latest}",
        (
            f"12M uploads vs prior: {total} vs {_format_number(prev)}"
            if prev
            else f"12M uploads: {total}"
        ),
        (
            f"YoY change: {yoy_pct:+.2f}% ({_format_number(yoy_change, '{:+,.0f}')})"
            if yoy_pct is not None
            else "YoY change: N/A"
        ),
        f"Rolling avg (6/12M): {rolling6} / {rolling12}",
        f"Trend slope: {slope:+.1f} papers/mo ({slope_pct:+.2f}%)",
    ]

    if cagr is not None:
        highlights.append(f"5Y CAGR: {cagr * 100:+.2f}%")
    highlights.append(f"Seasonality: peak {peak_str} · low {low_str}")
    return highlights


def _format_section(summary: dict, key: str, limit: int = 3) -> list[str]:
    records = summary.get(key, [])[:limit]
    lines = []
    for rec in records:
        cat = rec.get("main_cat", "N/A")
        yoy = rec.get("yoy_pct")
        delta = rec.get("absolute_change")
        share = rec.get("last12_share_pct")
        components = [cat]
        if yoy is not None:
            components.append(f"YoY {yoy:+.1f}%")
        if delta is not None:
            components.append(f"Δ {delta:+,}")
        if share is not None:
            components.append(f"Share {share:.1f}%")
        lines.append(", ".join(components))
    return lines


def _draw_bullets(
    c: canvas.Canvas,
    bullets: list[str],
    start_x: float,
    start_y: float,
    font: str = "Helvetica",
    size: int = 10,
    leading: float = 0.55,
) -> float:
    y = start_y
    c.setFont(font, size)
    for bullet in bullets:
        c.drawString(start_x, y, "• " + bullet)
        y -= leading * cm
    return y


def _draw_section(c: canvas.Canvas, title: str, lines: list[str], start_x: float, start_y: float) -> float:
    y = start_y
    if not lines:
        return y
    c.setFont("Helvetica-Bold", 10)
    c.drawString(start_x, y, title)
    y -= 0.32 * cm
    c.setFont("Helvetica", 8)
    for line in lines:
        c.drawString(start_x, y, line)
        y -= 0.34 * cm
    return y - 0.08 * cm


def _draw_metrics_panel(
    c: canvas.Canvas,
    summary: dict,
    start_x: float,
    start_y: float,
    width: float,
    height: float,
) -> float:
    seasonality = summary.get("seasonality") or {}
    strongest = seasonality.get("strongest_month")
    weakest = seasonality.get("weakest_month")
    month_map = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    }

    metrics = [
        ("12M Uploads", _format_number(summary.get("total_last12"))),
        (
            "YoY Change",
            (
                f"{summary.get('total_yoy_pct', 0):+.2f}% / "
                f"{_format_number(summary.get('total_yoy_change'), '{:+,.0f}')}"
                if summary.get("total_yoy_pct") is not None
                else "N/A"
            ),
        ),
        (
            "Rolling Avg (6/12M)",
            f"{_format_number(summary.get('rolling6_avg'), '{:,.0f}')} / "
            f"{_format_number(summary.get('rolling12_avg'), '{:,.0f}')}",
        ),
        (
            "Trend Slope (Δ / %)",
            f"{summary.get('trend_slope', 0):+.1f} / {summary.get('trend_slope_pct', 0):+.2f}%",
        ),
        (
            "Seasonality (Peak / Low)",
            f"{month_map.get(int(strongest), 'N/A') if strongest else 'N/A'} / "
            f"{month_map.get(int(weakest), 'N/A') if weakest else 'N/A'}",
        ),
    ]
    if summary.get("cagr_5yr") is not None:
        metrics.append(("5Y CAGR", f"{summary['cagr_5yr'] * 100:+.2f}%"))

    c.setFillColor(colors.whitesmoke)
    c.roundRect(start_x, start_y - height, width, height, 0.3 * cm, fill=True, stroke=0)
    c.setFillColor(colors.HexColor("#1f3a67"))
    c.roundRect(start_x, start_y - 0.6 * cm, width, 0.6 * cm, 0.3 * cm, fill=True, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(start_x + 0.35 * cm, start_y - 0.45 * cm, "Key Metrics")

    c.setFillColor(colors.black)
    col_count = 2
    col_width = (width - 0.6 * cm) / col_count
    rows = (len(metrics) + col_count - 1) // col_count
    row_height = (height - 1.0 * cm) / max(rows, 1)

    y = start_y - 0.9 * cm
    for idx, (label, value) in enumerate(metrics):
        col = idx % col_count
        cur_x = start_x + 0.35 * cm + col * col_width
        if idx > 0 and col == 0:
            y -= row_height
        c.setFont("Helvetica", 7.5)
        c.drawString(cur_x, y, label)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(cur_x, y - 0.24 * cm, str(value))

    return start_y - height - 0.4 * cm


def _dataset_note_lines(width: float) -> list[str]:
    text = (
        "Source: Kaggle 'arXiv Dataset' (Cornell University & collaborators, weekly STEM metadata updates). "
        "Scope: STEM titles, authors, abstracts, categories, and version history for 1.7M+ papers. "
        "Metadata license: CC0; check arXiv for per-paper terms."
    )
    max_chars = max(40, int(width / 5.0))
    return textwrap.wrap(text, width=max_chars)


def _draw_dataset_note(
    c: canvas.Canvas,
    lines: list[str],
    start_x: float,
    start_y: float,
    line_height: float,
) -> None:
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#555555"))
    y = start_y
    for line in lines:
        c.drawString(start_x, y, line)
        y -= line_height
    c.setFillColor(colors.black)


def _main(args: argparse.Namespace) -> int:
    assets = Assets(
        data=Path(args.data),
        total_fig=Path(args.fig1),
        growth_fig=Path(args.fig2),
        share_fig=Path(args.fig3),
        heatmap_fig=Path(args.fig4),
        scatter_fig=Path(args.fig5),
        volatility_fig=Path(args.fig6),
        summary_json=Path(args.summary),
        category_stats=Path(args.category_stats),
        output_pdf=Path(args.out),
    )
    summary, _ = _load_summary(assets)
    highlights = _build_highlights(summary)

    assets.output_pdf.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(assets.output_pdf), pagesize=landscape(A4))
    width, height = landscape(A4)
    margin = 1.4 * cm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, height - margin, "arXiv Research Trend Summary (Last 12 Months)")

    bullet_start = height - margin - 1.0 * cm
    c.setFont("Helvetica", 10)
    bullet_y = _draw_bullets(c, highlights, margin, bullet_start, size=8, leading=0.38)

    metrics_y = _draw_metrics_panel(
        c,
        summary,
        start_x=margin,
        start_y=bullet_y - 0.3 * cm,
        width=width - 2 * margin,
        height=2.6 * cm,
    )

    note_lines = _dataset_note_lines(width - 2 * margin)
    note_line_height = 0.24 * cm
    note_area_height = len(note_lines) * note_line_height + 0.6 * cm

    # Category sections
    col_width = (width - 2 * margin - 1 * cm) / 2
    section_y = metrics_y - 0.2 * cm
    left_x = margin
    right_x = margin + col_width + 1.0 * cm

    section_y_left = _draw_section(
        c,
        "Fastest Growing Categories",
        _format_section(summary, "top_growth"),
        left_x,
        section_y,
    )
    section_y_left = _draw_section(
        c,
        "Largest Categories (By Volume)",
        _format_section(summary, "top_volume"),
        left_x,
        section_y_left,
    )
    section_y_right = _draw_section(
        c,
        "Categories Losing Momentum",
        _format_section(summary, "top_decline"),
        right_x,
        section_y,
    )
    section_y_right = _draw_section(
        c,
        "Most Volatile Categories",
        _format_section(summary, "most_volatile"),
        right_x,
        section_y_right,
    )

    image_top = min(section_y_left, section_y_right) - 0.4 * cm
    available_width = width - 2 * margin
    gap = 0.35 * cm

    rows = [
        ([assets.total_fig, assets.growth_fig, assets.share_fig], 7.5 * cm),
        ([assets.heatmap_fig, assets.scatter_fig, assets.volatility_fig], 7.5 * cm),
    ]

    total_row_height = sum(height for _, height in rows) + gap * (len(rows) - 1)
    available_height = max(image_top - (margin + note_area_height), 0)
    scale = 1.0
    if total_row_height > 0:
        scale = min(1.0, available_height / total_row_height) if available_height > 0 else 0.0

    scaled_rows = [(paths, height * scale) for paths, height in rows]
    scaled_gap = gap * scale

    y = image_top
    for fig_paths, row_height in scaled_rows:
        if row_height <= 0:
            continue
        if len(fig_paths) == 1:
            fig_path = fig_paths[0]
            if fig_path.exists():
                c.drawImage(
                    str(fig_path),
                    margin,
                    y - row_height,
                    width=available_width,
                    height=row_height,
                    preserveAspectRatio=True,
                    anchor="sw",
                )
            else:
                c.setFont("Helvetica-Oblique", 10)
                c.drawString(margin, y - 0.5 * row_height, f"(Missing figure: {fig_path.name})")
            y -= row_height + scaled_gap
        else:
            half_width = (available_width - (len(fig_paths) - 1) * scaled_gap) / len(fig_paths)
            current_x = margin
            for fig_path in fig_paths:
                if fig_path.exists():
                    c.drawImage(
                        str(fig_path),
                        current_x,
                        y - row_height,
                        width=half_width,
                        height=row_height,
                        preserveAspectRatio=True,
                        anchor="sw",
                    )
                else:
                    c.setFont("Helvetica-Oblique", 10)
                    c.drawString(current_x, y - 0.5 * row_height, f"(Missing figure: {fig_path.name})")
                current_x += half_width + scaled_gap
            y -= row_height + scaled_gap

    note_start_y = margin + note_area_height - note_line_height
    _draw_dataset_note(c, note_lines, margin, note_start_y, note_line_height)

    c.showPage()
    c.save()
    print(f"Saved → {assets.output_pdf.resolve()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a one-page PDF summary for arXiv trends.")
    parser.add_argument("--data", default="data/arxiv_monthly.csv", help="Aggregate CSV path")
    parser.add_argument("--fig1", default="figures/01_monthly_total.png", help="Monthly trend figure")
    parser.add_argument("--fig2", default="figures/02_top_growth.png", help="Growth chart figure")
    parser.add_argument("--fig3", default="figures/03_top_share.png", help="Share chart figure")
    parser.add_argument("--fig4", default="figures/04_category_heatmap.png", help="Category heatmap figure")
    parser.add_argument("--fig5", default="figures/05_growth_vs_volume.png", help="Growth vs volume scatter figure")
    parser.add_argument("--fig6", default="figures/06_volatility.png", help="Volatility chart figure")
    parser.add_argument("--summary", default="data/arxiv_summary.json", help="Summary JSON path")
    parser.add_argument("--category-stats", default="data/arxiv_category_stats.csv", help="Category statistics CSV path")
    parser.add_argument("--out", default="report_onepager.pdf", help="Output PDF path")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(_main(args))


if __name__ == "__main__":
    main()
