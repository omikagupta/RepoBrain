"""Render the published preliminary summary into a portable SVG."""

import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODES = ("lexical", "vector", "hybrid", "graph-enhanced")
COLORS = ("#64748b", "#0284c7", "#4338ca", "#047857")


def main() -> None:
    summary = json.loads((ROOT / "results/run-01-summary.json").read_bytes())
    rows = {(row["group"], row["mode"]): row for row in summary["breakdowns"]}
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="900" '
        'viewBox="0 0 900 900" role="img" aria-labelledby="title">',
        '<title id="title">Preliminary benchmark-v1 results</title>',
        '<rect width="900" height="900" fill="#f8fafc"/>',
    ]

    def text(x: float, y: float, label: str, size: int = 15) -> None:
        svg.append(
            f'<text x="{x}" y="{y}" font-family="system-ui,sans-serif" '
            f'font-size="{size}" fill="#0f172a">{escape(label)}</text>'
        )

    text(32, 40, "RepoBrain retrieval benchmark v1", 26)
    text(32, 68, "Preliminary · machine-assisted labels · 600 measured attempts")
    panels = [
        ("Cross-file Evidence Recall@10", "category/cross-file", "recall@10", 1),
        (
            "Cross-file Essential Evidence Coverage@10",
            "category/cross-file",
            "essential_coverage@10",
            1,
        ),
        (
            "Cross-file latency · median and P95",
            "category/cross-file",
            "median_ms",
            130,
        ),
        ("Tomli Evidence Recall@10", "repository/hukkin/tomli", "recall@10", 1),
        (
            "Humanize Evidence Recall@10",
            "repository/python-humanize/humanize",
            "recall@10",
            1,
        ),
        ("uiri/toml Evidence Recall@10", "repository/uiri/toml", "recall@10", 1),
    ]
    for index, (title, group, field, scale) in enumerate(panels):
        x, y = 32 + 438 * (index % 2), 105 + 225 * (index // 2)
        text(x, y, title, 17)
        for offset, (mode, color) in enumerate(zip(MODES, COLORS, strict=True)):
            row = rows[group, mode]
            value = row[field] if scale > 1 else row["metrics"][field]["mean"]
            yy = y + 40 + offset * 39
            text(x, yy, mode)
            width = 195 * value / scale
            svg.append(
                f'<rect x="{x + 123}" y="{yy - 13}" width="{width:.3f}" '
                f'height="15" rx="3" fill="{color}"/>'
            )
            label = f"{value:.1f} ms" if scale > 1 else f"{value:.1%}"
            if scale > 1:
                p95 = x + 123 + 195 * row["p95_ms"] / scale
                svg.append(
                    f'<line x1="{p95}" x2="{p95}" y1="{yy - 15}" '
                    f'y2="{yy + 4}" stroke="#0f172a" stroke-width="2"/>'
                )
                label = f"{value:.1f} / {row['p95_ms']:.1f}"
            text(x + 324, yy, label, 13)
    paired = next(
        item for item in summary["comparisons"] if item["baseline"] == "hybrid"
    )
    mean, low, high = paired["bootstrap_mean_low_high"]
    text(32, 800, "Graph-enhanced minus hybrid · cross-file Recall@10", 18)
    text(
        32,
        824,
        f"{mean:+.2%} · 95% paired interval {low:+.2%} to {high:+.2%} · inconclusive",
    )
    origin = 450
    svg.append('<line x1="450" x2="450" y1="833" y2="873" stroke="#64748b"/>')
    svg.append(
        f'<line x1="{origin + 2400 * low}" x2="{origin + 2400 * high}" '
        'y1="853" y2="853" stroke="#4338ca" stroke-width="4"/>'
    )
    svg.append(f'<circle cx="{origin + 2400 * mean}" cy="853" r="7" fill="#4338ca"/>')
    svg.append("</svg>")
    (ROOT / "results/run-01-plots.svg").write_text(
        "\n".join(svg) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
