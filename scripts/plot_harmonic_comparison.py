#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
from dataclasses import dataclass
from pathlib import Path


BG_COLOR = "#ffffff"
PANEL_BG = "#fbfcfe"
GRID_COLOR = "#d9dfe8"
TEXT_COLOR = "#1f2933"
AXIS_COLOR = "#6b7785"
BASELINE_COLOR = "#94a3b8"

SERIES_COLORS = ["#0f766e", "#2563eb", "#d97706", "#b45309"]


@dataclass
class ChangeSummary:
    first: float
    last: float
    delta: float
    delta_percent: float


@dataclass
class SampleData:
    label: str
    path: Path
    measurements: list[int]
    h3_values: list[float]
    h5_values: list[float]
    h3_relative: list[float]
    h5_relative: list[float]
    h3_summary: ChangeSummary
    h5_summary: ChangeSummary
    freq_label: str


def parse_series_arg(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            "series 参数格式应为 标签=CSV路径，例如 水凝胶=data/foo.csv"
        )
    label, raw_path = raw.split("=", 1)
    label = label.strip()
    path = Path(raw_path.strip())
    if not label:
        raise argparse.ArgumentTypeError("series 标签不能为空")
    if not path.exists():
        raise argparse.ArgumentTypeError(f"找不到文件: {path}")
    return label, path


def relative_to_first(values: list[float]) -> list[float]:
    first = values[0]
    if first == 0:
        return [0.0 for _ in values]
    return [(value - first) / first * 100.0 for value in values]


def summarize_change(values: list[float]) -> ChangeSummary:
    first = values[0]
    last = values[-1]
    delta = last - first
    delta_percent = delta / first * 100.0 if first != 0 else float("nan")
    return ChangeSummary(
        first=first,
        last=last,
        delta=delta,
        delta_percent=delta_percent,
    )


def load_sample(label: str, path: Path) -> SampleData:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise ValueError(f"CSV 为空: {path}")

    measurements = [int(row["measurement_index"]) for row in rows]
    h3_values = [float(row["harmonic_3_magnitude"]) for row in rows]
    h5_values = [float(row["harmonic_5_magnitude"]) for row in rows]
    freq_hz = float(rows[0]["frequency_hz"])
    freq_label = f"{int(freq_hz)}Hz" if freq_hz.is_integer() else f"{freq_hz:g}Hz"

    return SampleData(
        label=label,
        path=path,
        measurements=measurements,
        h3_values=h3_values,
        h5_values=h5_values,
        h3_relative=relative_to_first(h3_values),
        h5_relative=relative_to_first(h5_values),
        h3_summary=summarize_change(h3_values),
        h5_summary=summarize_change(h5_values),
        freq_label=freq_label,
    )


def fmt_value(value: float) -> str:
    return f"{value:.4f}"


def fmt_percent(value: float) -> str:
    return f"{value:+.2f}%"


def build_svg(samples: list[SampleData], output_path: Path, minimal: bool = False) -> None:
    width = 1500 if minimal else 1600
    height = 820 if minimal else 980
    left = 90
    plot_width = 1320 if minimal else 980
    stats_x = left + plot_width + 36
    stats_width = 400
    panel_height = 280
    panel_gap = 70 if minimal else 80
    top_first = 140 if minimal else 220
    top_second = top_first + panel_height + panel_gap

    x_min = min(min(sample.measurements) for sample in samples)
    x_max = max(max(sample.measurements) for sample in samples)
    if x_min == x_max:
        x_max = x_min + 1

    def build_panel(
        panel_top: int,
        panel_title: str,
        value_getter: str,
        lines: list[str],
    ) -> None:
        plot_bottom = panel_top + panel_height
        plot_right = left + plot_width

        all_values = [
            value
            for sample in samples
            for value in getattr(sample, value_getter)
        ]
        y_min = min(all_values)
        y_max = max(all_values)
        y_min = min(y_min, 0.0)
        y_max = max(y_max, 0.0)
        y_range = y_max - y_min
        padding = y_range * 0.12 if y_range else 2.0
        y_min -= padding
        y_max += padding

        def scale_x(value: float) -> float:
            return left + (value - x_min) / (x_max - x_min) * plot_width

        def scale_y(value: float) -> float:
            return plot_bottom - (value - y_min) / (y_max - y_min) * panel_height

        y_ticks = 6
        x_tick_count = min(10, x_max - x_min + 1)
        x_ticks = sorted(
            {
                round(x_min + (x_max - x_min) * index / max(x_tick_count - 1, 1))
                for index in range(x_tick_count)
            }
        )

        lines.extend(
            [
                f'<rect x="{left}" y="{panel_top}" width="{plot_width}" height="{panel_height}" fill="{PANEL_BG}" stroke="#c7d0db"/>',
                f'<text x="{left}" y="{panel_top - 22}" font-size="26" font-weight="700" font-family="Noto Sans SC, Microsoft YaHei, sans-serif" fill="{TEXT_COLOR}">{html.escape(panel_title)}</text>',
            ]
        )

        for index in range(y_ticks):
            ratio = index / (y_ticks - 1)
            y_value = y_max - ratio * (y_max - y_min)
            y_pos = scale_y(y_value)
            lines.append(
                f'<line x1="{left}" y1="{y_pos:.2f}" x2="{plot_right}" y2="{y_pos:.2f}" stroke="{GRID_COLOR}" stroke-width="1"/>'
            )
            lines.append(
                f'<text x="{left - 14}" y="{y_pos + 5:.2f}" text-anchor="end" font-size="14" font-family="Noto Sans SC, Microsoft YaHei, sans-serif" fill="{TEXT_COLOR}">{y_value:.1f}%</text>'
            )

        for tick in x_ticks:
            x_pos = scale_x(tick)
            lines.append(
                f'<line x1="{x_pos:.2f}" y1="{panel_top}" x2="{x_pos:.2f}" y2="{plot_bottom}" stroke="{GRID_COLOR}" stroke-width="1"/>'
            )
            lines.append(
                f'<text x="{x_pos:.2f}" y="{plot_bottom + 28}" text-anchor="middle" font-size="14" font-family="Noto Sans SC, Microsoft YaHei, sans-serif" fill="{TEXT_COLOR}">{tick}</text>'
            )

        baseline_y = scale_y(0.0)
        lines.extend(
            [
                f'<line x1="{left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>',
                f'<line x1="{left}" y1="{panel_top}" x2="{left}" y2="{plot_bottom}" stroke="{AXIS_COLOR}" stroke-width="1.5"/>',
                f'<line x1="{left}" y1="{baseline_y:.2f}" x2="{plot_right}" y2="{baseline_y:.2f}" stroke="{BASELINE_COLOR}" stroke-width="2" stroke-dasharray="8 6"/>',
            ]
        )

        end_labels: list[tuple[float, str, str]] = []
        for index, sample in enumerate(samples):
            color = SERIES_COLORS[index % len(SERIES_COLORS)]
            values = getattr(sample, value_getter)
            points = " ".join(
                f"{scale_x(x):.2f},{scale_y(y):.2f}"
                for x, y in zip(sample.measurements, values)
            )
            lines.append(
                f'<polyline fill="none" stroke="{color}" stroke-width="3.2" points="{points}"/>'
            )

            start_x = scale_x(sample.measurements[0])
            start_y = scale_y(values[0])
            end_x = scale_x(sample.measurements[-1])
            end_y = scale_y(values[-1])
            lines.append(
                f'<circle cx="{start_x:.2f}" cy="{start_y:.2f}" r="5" fill="{color}" stroke="#ffffff" stroke-width="2"/>'
            )
            lines.append(
                f'<circle cx="{end_x:.2f}" cy="{end_y:.2f}" r="5.5" fill="#ffffff" stroke="{color}" stroke-width="3"/>'
            )
            end_labels.append(
                (
                    end_y,
                    color,
                    f"{sample.label} {fmt_percent(values[-1])}",
                )
            )

        end_labels.sort(key=lambda item: item[0])
        for index, (end_y, color, text) in enumerate(end_labels):
            label_y = end_y - 10 if index == 0 else end_y + 22
            lines.append(
                f'<text x="{plot_right - 10}" y="{label_y:.2f}" text-anchor="end" font-size="14" font-weight="700" font-family="Noto Sans SC, Microsoft YaHei, sans-serif" fill="{color}">{html.escape(text)}</text>'
            )

        lines.extend(
            [
                f'<text x="{left + plot_width / 2:.2f}" y="{plot_bottom + 56}" text-anchor="middle" font-size="18" font-family="Noto Sans SC, Microsoft YaHei, sans-serif" fill="{TEXT_COLOR}">Measurement Index</text>',
                f'<text x="34" y="{panel_top + panel_height / 2:.2f}" transform="rotate(-90 34 {panel_top + panel_height / 2:.2f})" text-anchor="middle" font-size="18" font-family="Noto Sans SC, Microsoft YaHei, sans-serif" fill="{TEXT_COLOR}">Relative Change vs First Measurement</text>',
            ]
        )
    freq_label = samples[0].freq_label

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{BG_COLOR}"/>',
        f'<text x="{left}" y="56" font-size="32" font-weight="700" font-family="Noto Sans SC, Microsoft YaHei, sans-serif" fill="{TEXT_COLOR}">水凝胶 vs test_synomag_2ug 谐波趋势对比</text>',
        f'<text x="{left}" y="84" font-size="16" font-family="Noto Sans SC, Microsoft YaHei, sans-serif" fill="#52606d">{freq_label} | 所有曲线已按各自首测归一化，因此 0% 代表第 1 次测量值</text>',
    ]

    legend_x = left + plot_width - 290 if minimal else left + 980
    for index, sample in enumerate(samples):
        color = SERIES_COLORS[index % len(SERIES_COLORS)]
        y = 110 + index * 24
        svg_lines.extend(
            [
                f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 34}" y2="{y}" stroke="{color}" stroke-width="5"/>',
                f'<text x="{legend_x + 46}" y="{y + 6}" font-size="15" font-family="Noto Sans SC, Microsoft YaHei, sans-serif" fill="{TEXT_COLOR}">{html.escape(sample.label)}</text>',
            ]
        )

    build_panel(
        panel_top=top_first,
        panel_title="第三谐波相对变化",
        value_getter="h3_relative",
        lines=svg_lines,
    )
    build_panel(
        panel_top=top_second,
        panel_title="第五谐波相对变化",
        value_getter="h5_relative",
        lines=svg_lines,
    )

    svg_lines.extend(
        [
            f'<text x="{width - 22}" y="{height - 18}" text-anchor="end" font-size="12" font-family="Noto Sans SC, Microsoft YaHei, sans-serif" fill="#6b7785">Generated by scripts/plot_harmonic_comparison.py</text>',
            "</svg>",
        ]
    )

    output_path.write_text("\n".join(svg_lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将多个谐波 CSV 合并为一张趋势对比图，默认使用相对首测变化(%)。"
    )
    parser.add_argument(
        "--series",
        action="append",
        required=True,
        help="格式为 标签=CSV路径，可重复传入两次或更多次。",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="输出 SVG 路径。",
    )
    parser.add_argument(
        "--minimal",
        action="store_true",
        help="生成精简版图像，移除顶部摘要和右侧统计框。",
    )
    args = parser.parse_args()

    parsed_series = [parse_series_arg(raw) for raw in args.series]
    samples = [load_sample(label, path) for label, path in parsed_series]
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_svg(samples, output_path, minimal=args.minimal)

    print(f"已生成对比图: {output_path}")


if __name__ == "__main__":
    main()
