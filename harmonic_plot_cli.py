#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import math
import shlex
import statistics as st
from dataclasses import dataclass
from pathlib import Path


H3_COLOR = "#1d70b8"
H5_COLOR = "#d95f02"
RATIO_COLOR = "#2f855a"
TREND_COLOR = "#5f6368"
GRID_COLOR = "#d9dfe8"
TEXT_COLOR = "#1f2933"
BG_COLOR = "#ffffff"


@dataclass
class HarmonicStats:
    count: int
    minimum: float
    maximum: float
    mean: float
    std: float
    cv_percent: float
    slope_per_measurement: float
    intercept: float
    first_value: float
    last_value: float
    drift_value: float
    drift_percent_of_mean: float


def normalize_dragged_path(raw: str, base_dir: Path | None = None) -> Path:
    text = raw.strip()
    if not text:
        raise ValueError("输入为空。")

    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    else:
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = [text]
        if len(parts) == 1:
            text = parts[0]

    path = Path(text).expanduser()
    if base_dir and not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def prompt_for_directory(cli_value: str | None) -> Path:
    if cli_value:
        directory = normalize_dragged_path(cli_value)
        if not directory.is_dir():
            raise ValueError(f"文件夹不存在: {directory}")
        return directory

    default = Path.cwd().resolve()
    while True:
        raw = input(f"请把数据文件夹拖到这里后回车 [默认: {default}]: ").strip()
        if not raw:
            return default

        try:
            directory = normalize_dragged_path(raw)
        except ValueError as exc:
            print(f"路径读取失败: {exc}")
            continue

        if directory.is_dir():
            return directory

        print(f"这不是一个有效文件夹: {directory}")


def path_is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def find_candidate_files(directory: Path) -> list[Path]:
    preferred = sorted(directory.glob("*Spectra*.txt"))
    if preferred:
        return preferred
    return sorted(directory.glob("*.txt"))


def resolve_file_and_directory(
    file_arg: str | None,
    folder_arg: str | None,
) -> tuple[Path | None, Path | None]:
    selected_dir: Path | None = None
    selected_file: Path | None = None

    if folder_arg:
        selected_dir = prompt_for_directory(folder_arg)

    if file_arg:
        base_dir = selected_dir or Path.cwd().resolve()
        candidate = normalize_dragged_path(file_arg, base_dir=base_dir)

        if candidate.is_dir():
            if selected_dir and candidate.resolve() != selected_dir.resolve():
                raise ValueError("`--folder` 和 `--file` 指向了不同文件夹。")
            selected_dir = candidate
        elif candidate.is_file():
            selected_file = candidate
            if selected_dir and not path_is_within(selected_file, selected_dir):
                raise ValueError("所选文件不在 `--folder` 指定的文件夹中。")
            selected_dir = selected_file.parent
        else:
            raise ValueError(f"路径不存在: {candidate}")

    return selected_file, selected_dir


def prompt_for_direct_file(
    cli_value: str | None,
    base_dir: Path | None = None,
    prompt_text: str = "请把 Spectra 文件拖到这里后回车: ",
) -> tuple[Path, Path]:
    if cli_value:
        candidate = normalize_dragged_path(cli_value, base_dir=base_dir)
        if candidate.is_file():
            return candidate, candidate.parent
        if candidate.is_dir():
            return prompt_for_file(candidate, None), candidate
        raise ValueError(f"路径不存在: {candidate}")

    while True:
        raw = input(prompt_text).strip()
        try:
            candidate = normalize_dragged_path(raw, base_dir=base_dir)
        except ValueError as exc:
            print(f"路径读取失败: {exc}")
            continue

        if candidate.is_file():
            return candidate, candidate.parent

        if candidate.is_dir():
            print("检测到你拖入的是文件夹，我也可以继续帮你选文件。")
            return prompt_for_file(candidate, None), candidate

        print(f"文件不存在: {candidate}")


def prompt_for_file(directory: Path, cli_value: str | None) -> Path:
    candidates = find_candidate_files(directory)
    if cli_value:
        selected = normalize_dragged_path(cli_value, base_dir=directory)
        if not selected.is_file():
            raise ValueError(f"文件不存在: {selected}")
        if not path_is_within(selected, directory):
            raise ValueError("所选文件不在刚才选择的文件夹中。")
        return selected

    if candidates:
        print("\n当前文件夹中的候选文件:")
        for index, path in enumerate(candidates, start=1):
            print(f"  {index:>2}. {path.name}")
        print("输入序号、文件名，或者直接把目标文件拖到这里。")
    else:
        print("\n这个文件夹里没有找到 `.txt` 文件，请直接把目标文件拖到这里。")

    while True:
        raw = input("请选择文件: ").strip()
        if raw.isdigit() and candidates:
            index = int(raw)
            if 1 <= index <= len(candidates):
                return candidates[index - 1]
            print("序号超出范围，请重新输入。")
            continue

        try:
            selected = normalize_dragged_path(raw, base_dir=directory)
        except ValueError as exc:
            print(f"路径读取失败: {exc}")
            continue

        if not selected.is_file():
            print(f"文件不存在: {selected}")
            continue
        if not path_is_within(selected, directory):
            print("这个文件不在刚才选择的文件夹中，请重新选择。")
            continue
        return selected


def harmonic_pair(values: list[float], harmonic: int) -> tuple[float, float]:
    pair_start = 2 + (harmonic - 1) * 2
    if len(values) <= pair_start + 1:
        raise ValueError(
            f"数据列数不足，无法读取 {harmonic} 次谐波。"
        )
    real = values[pair_start]
    imag = values[pair_start + 1]
    return real, imag


def parse_spectra_file(path: Path) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    with path.open("r", encoding="utf-8") as infile:
        for index, line in enumerate(infile, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            values = [float(part) for part in stripped.split()]
            if len(values) < 12:
                raise ValueError(
                    f"{path.name} 看起来不是 Spectra 文件: 第 {index} 行只有 {len(values)} 列。"
                )

            h3_real, h3_imag = harmonic_pair(values, 3)
            h5_real, h5_imag = harmonic_pair(values, 5)
            h3_magnitude = math.hypot(h3_real, h3_imag)
            h5_magnitude = math.hypot(h5_real, h5_imag)

            rows.append(
                {
                    "measurement_index": len(rows) + 1,
                    "frequency_hz": values[0],
                    "excitation": values[1],
                    "harmonic_3_real": h3_real,
                    "harmonic_3_imag": h3_imag,
                    "harmonic_3_magnitude": h3_magnitude,
                    "harmonic_5_real": h5_real,
                    "harmonic_5_imag": h5_imag,
                    "harmonic_5_magnitude": h5_magnitude,
                    "harmonic_5_over_3": h5_magnitude / h3_magnitude
                    if h3_magnitude
                    else float("nan"),
                }
            )

    if not rows:
        raise ValueError(f"{path.name} 没有可读取的数据行。")
    return rows


def linear_fit(values: list[float]) -> tuple[float, float]:
    if len(values) == 1:
        return 0.0, values[0]

    x_values = [float(index) for index in range(1, len(values) + 1)]
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(values) / len(values)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    slope = numerator / denominator if denominator else 0.0
    intercept = y_mean - slope * x_mean
    return slope, intercept


def calc_stats(values: list[float]) -> HarmonicStats:
    mean_value = sum(values) / len(values)
    std_value = st.stdev(values) if len(values) > 1 else 0.0
    cv_percent = std_value / mean_value * 100.0 if mean_value else float("nan")
    first_value = values[0]
    last_value = values[-1]
    slope, intercept = linear_fit(values)
    drift_value = last_value - first_value
    drift_percent_of_mean = drift_value / mean_value * 100.0 if mean_value else float("nan")
    return HarmonicStats(
        count=len(values),
        minimum=min(values),
        maximum=max(values),
        mean=mean_value,
        std=std_value,
        cv_percent=cv_percent,
        slope_per_measurement=slope,
        intercept=intercept,
        first_value=first_value,
        last_value=last_value,
        drift_value=drift_value,
        drift_percent_of_mean=drift_percent_of_mean,
    )


def make_output_dir(selected_dir: Path, cli_value: str | None) -> Path:
    if cli_value:
        output_dir = normalize_dragged_path(cli_value)
    elif selected_dir.name.endswith("_summary"):
        output_dir = selected_dir
    else:
        output_dir = selected_dir.parent / f"{selected_dir.name}_summary"

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def frequency_tag(rows: list[dict[str, float | int]]) -> str:
    freqs = [float(row["frequency_hz"]) for row in rows]
    first = freqs[0]
    if all(abs(freq - first) < 1e-9 for freq in freqs):
        rounded = round(first)
        if abs(first - rounded) < 1e-9:
            return f"{rounded}Hz"
        return f"{first:g}Hz"
    return "mixed_frequency"


def write_combined_csv(path: Path, rows: list[dict[str, float | int]]) -> None:
    fieldnames = [
        "measurement_index",
        "frequency_hz",
        "excitation",
        "harmonic_3_real",
        "harmonic_3_imag",
        "harmonic_3_magnitude",
        "harmonic_5_real",
        "harmonic_5_imag",
        "harmonic_5_magnitude",
        "harmonic_5_over_3",
    ]
    with path.open("w", encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_analysis_txt(
    path: Path,
    source_file: Path,
    output_dir: Path,
    freq_label: str,
    h3_stats: HarmonicStats,
    h5_stats: HarmonicStats,
    ratio_stats: HarmonicStats,
) -> None:
    lines = [
        f"{source_file.stem} {freq_label} Harmonic Analysis",
        f"source_file\t{source_file}",
        f"output_dir\t{output_dir}",
        "",
        "[harmonic_3]",
        f"measurement_count\t{h3_stats.count}",
        f"magnitude_min\t{h3_stats.minimum:.12f}",
        f"magnitude_max\t{h3_stats.maximum:.12f}",
        f"magnitude_mean\t{h3_stats.mean:.12f}",
        f"magnitude_std\t{h3_stats.std:.12f}",
        f"cv_percent\t{h3_stats.cv_percent:.6f}",
        f"linear_slope_per_measurement\t{h3_stats.slope_per_measurement:.12e}",
        f"first_value\t{h3_stats.first_value:.12f}",
        f"last_value\t{h3_stats.last_value:.12f}",
        f"drift_last_minus_first\t{h3_stats.drift_value:.12f}",
        f"drift_percent_of_mean\t{h3_stats.drift_percent_of_mean:.6f}",
        "",
        "[harmonic_5]",
        f"measurement_count\t{h5_stats.count}",
        f"magnitude_min\t{h5_stats.minimum:.12f}",
        f"magnitude_max\t{h5_stats.maximum:.12f}",
        f"magnitude_mean\t{h5_stats.mean:.12f}",
        f"magnitude_std\t{h5_stats.std:.12f}",
        f"cv_percent\t{h5_stats.cv_percent:.6f}",
        f"linear_slope_per_measurement\t{h5_stats.slope_per_measurement:.12e}",
        f"first_value\t{h5_stats.first_value:.12f}",
        f"last_value\t{h5_stats.last_value:.12f}",
        f"drift_last_minus_first\t{h5_stats.drift_value:.12f}",
        f"drift_percent_of_mean\t{h5_stats.drift_percent_of_mean:.6f}",
        "",
        "[harmonic_5_over_3]",
        f"measurement_count\t{ratio_stats.count}",
        f"magnitude_min\t{ratio_stats.minimum:.12f}",
        f"magnitude_max\t{ratio_stats.maximum:.12f}",
        f"magnitude_mean\t{ratio_stats.mean:.12f}",
        f"magnitude_std\t{ratio_stats.std:.12f}",
        f"cv_percent\t{ratio_stats.cv_percent:.6f}",
        f"linear_slope_per_measurement\t{ratio_stats.slope_per_measurement:.12e}",
        f"first_value\t{ratio_stats.first_value:.12f}",
        f"last_value\t{ratio_stats.last_value:.12f}",
        f"drift_last_minus_first\t{ratio_stats.drift_value:.12f}",
        f"drift_percent_of_mean\t{ratio_stats.drift_percent_of_mean:.6f}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def fmt_float(value: float) -> str:
    return f"{value:.6f}"


def build_svg_plot(
    path: Path,
    file_name: str,
    freq_label: str,
    harmonic_label: str,
    color: str,
    measurements: list[int],
    magnitudes: list[float],
    stats: HarmonicStats,
) -> None:
    width = 1400
    height = 760
    left = 90
    top = 100
    bottom = 90
    plot_width = 900
    plot_height = 540
    plot_right = left + plot_width
    plot_bottom = top + plot_height
    stats_x = plot_right + 35
    stats_y = 150
    stats_width = 280
    stats_height = 275

    x_min = min(measurements)
    x_max = max(measurements)
    if x_min == x_max:
        x_max = x_min + 1

    y_min = min(magnitudes)
    y_max = max(magnitudes)
    y_range = y_max - y_min
    padding = y_range * 0.08 if y_range else max(abs(y_min) * 0.08, 1e-6)
    y_min -= padding
    y_max += padding

    def scale_x(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_width

    def scale_y(value: float) -> float:
        return plot_bottom - (value - y_min) / (y_max - y_min) * plot_height

    points = " ".join(
        f"{scale_x(x):.2f},{scale_y(y):.2f}"
        for x, y in zip(measurements, magnitudes)
    )

    trend_start_y = stats.intercept + stats.slope_per_measurement * x_min
    trend_end_y = stats.intercept + stats.slope_per_measurement * max(measurements)
    trend_points = (
        f"{scale_x(x_min):.2f},{scale_y(trend_start_y):.2f} "
        f"{scale_x(max(measurements)):.2f},{scale_y(trend_end_y):.2f}"
    )

    y_ticks = 6
    x_tick_count = min(10, len(measurements))
    if len(measurements) == 1:
        x_ticks = [measurements[0]]
    else:
        x_ticks = sorted(
            {
                round(x_min + (x_max - x_min) * index / max(x_tick_count - 1, 1))
                for index in range(x_tick_count)
            }
        )

    stats_lines = [
        f"Count: {stats.count}",
        f"Min: {fmt_float(stats.minimum)}",
        f"Max: {fmt_float(stats.maximum)}",
        f"Mean: {fmt_float(stats.mean)}",
        f"Std: {fmt_float(stats.std)}",
        f"CV: {stats.cv_percent:.4f}%",
        f"Slope: {stats.slope_per_measurement:.3e}",
        f"Drift: {stats.drift_percent_of_mean:+.4f}%",
    ]

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{BG_COLOR}"/>',
        '<text x="90" y="56" font-size="28" font-weight="700" '
        'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
        f'fill="{TEXT_COLOR}">{html.escape(harmonic_label)} Trend</text>',
        '<text x="90" y="84" font-size="16" '
        'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
        f'fill="{TEXT_COLOR}">{html.escape(file_name)} | {html.escape(freq_label)}</text>',
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#fbfcfe" stroke="#c7d0db"/>',
    ]

    for index in range(y_ticks):
        ratio = index / (y_ticks - 1)
        y_value = y_max - ratio * (y_max - y_min)
        y_pos = scale_y(y_value)
        svg_lines.append(
            f'<line x1="{left}" y1="{y_pos:.2f}" x2="{plot_right}" y2="{y_pos:.2f}" '
            f'stroke="{GRID_COLOR}" stroke-width="1"/>'
        )
        svg_lines.append(
            f'<text x="{left - 12}" y="{y_pos + 5:.2f}" text-anchor="end" font-size="14" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">{fmt_float(y_value)}</text>'
        )

    for tick in x_ticks:
        x_pos = scale_x(tick)
        svg_lines.append(
            f'<line x1="{x_pos:.2f}" y1="{top}" x2="{x_pos:.2f}" y2="{plot_bottom}" '
            f'stroke="{GRID_COLOR}" stroke-width="1"/>'
        )
        svg_lines.append(
            f'<text x="{x_pos:.2f}" y="{plot_bottom + 30}" text-anchor="middle" font-size="14" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">{tick}</text>'
        )

    svg_lines.extend(
        [
            f'<line x1="{left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="#6b7785" stroke-width="1.5"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{plot_bottom}" stroke="#6b7785" stroke-width="1.5"/>',
            f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{points}"/>',
            f'<polyline fill="none" stroke="{TREND_COLOR}" stroke-width="2" stroke-dasharray="8 6" points="{trend_points}"/>',
        ]
    )

    for x_value, y_value in zip(measurements, magnitudes):
        svg_lines.append(
            f'<circle cx="{scale_x(x_value):.2f}" cy="{scale_y(y_value):.2f}" r="4.2" '
            f'fill="{color}" opacity="0.92"/>'
        )

    svg_lines.extend(
        [
            f'<text x="{left + plot_width / 2:.2f}" y="{height - 28}" text-anchor="middle" font-size="18" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Measurement Index</text>',
            f'<text x="34" y="{top + plot_height / 2:.2f}" transform="rotate(-90 34 {top + plot_height / 2:.2f})" '
            'text-anchor="middle" font-size="18" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Magnitude</text>',
            f'<rect x="{stats_x}" y="{stats_y}" width="{stats_width}" height="{stats_height}" rx="14" fill="#f6f8fb" stroke="#d7dee7"/>',
            f'<text x="{stats_x + 20}" y="{stats_y + 34}" font-size="20" font-weight="700" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Quick Stats</text>',
        ]
    )

    for line_index, text in enumerate(stats_lines, start=1):
        svg_lines.append(
            f'<text x="{stats_x + 20}" y="{stats_y + 34 + line_index * 28}" font-size="16" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">{html.escape(text)}</text>'
        )

    legend_y = stats_y + stats_height + 36
    svg_lines.extend(
        [
            f'<line x1="{stats_x}" y1="{legend_y}" x2="{stats_x + 32}" y2="{legend_y}" stroke="{color}" stroke-width="4"/>',
            f'<text x="{stats_x + 44}" y="{legend_y + 6}" font-size="15" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Measured magnitude</text>',
            f'<line x1="{stats_x}" y1="{legend_y + 32}" x2="{stats_x + 32}" y2="{legend_y + 32}" stroke="{TREND_COLOR}" stroke-width="3" stroke-dasharray="8 6"/>',
            f'<text x="{stats_x + 44}" y="{legend_y + 38}" font-size="15" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Linear trend</text>',
            f'<text x="{width - 22}" y="{height - 18}" text-anchor="end" font-size="12" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="#6b7785">Generated by harmonic_plot_cli.py</text>',
            "</svg>",
        ]
    )

    path.write_text("\n".join(svg_lines), encoding="utf-8")


def process_selected_file(
    selected_file: Path,
    selected_dir: Path,
    output_arg: str | None,
) -> None:
    output_dir = make_output_dir(selected_dir, output_arg)
    rows = parse_spectra_file(selected_file)

    h3_values = [float(row["harmonic_3_magnitude"]) for row in rows]
    h5_values = [float(row["harmonic_5_magnitude"]) for row in rows]
    ratio_values = [float(row["harmonic_5_over_3"]) for row in rows]
    measurements = [int(row["measurement_index"]) for row in rows]

    h3_stats = calc_stats(h3_values)
    h5_stats = calc_stats(h5_values)
    ratio_stats = calc_stats(ratio_values)
    freq_label = frequency_tag(rows)

    csv_path = output_dir / f"{selected_file.stem}_harmonics_3_5_{freq_label}.csv"
    txt_path = output_dir / f"{selected_file.stem}_harmonics_3_5_analysis_{freq_label}.txt"
    h3_svg_path = output_dir / f"{selected_file.stem}_harmonic_3_trend_{freq_label}.svg"
    h5_svg_path = output_dir / f"{selected_file.stem}_harmonic_5_trend_{freq_label}.svg"
    ratio_svg_path = output_dir / f"{selected_file.stem}_harmonic_5_over_3_trend_{freq_label}.svg"

    write_combined_csv(csv_path, rows)
    write_analysis_txt(
        txt_path,
        selected_file,
        output_dir,
        freq_label,
        h3_stats,
        h5_stats,
        ratio_stats,
    )
    build_svg_plot(
        h3_svg_path,
        selected_file.name,
        freq_label,
        "Harmonic 3 Magnitude",
        H3_COLOR,
        measurements,
        h3_values,
        h3_stats,
    )
    build_svg_plot(
        h5_svg_path,
        selected_file.name,
        freq_label,
        "Harmonic 5 Magnitude",
        H5_COLOR,
        measurements,
        h5_values,
        h5_stats,
    )
    build_svg_plot(
        ratio_svg_path,
        selected_file.name,
        freq_label,
        "Harmonic 5 / Harmonic 3",
        RATIO_COLOR,
        measurements,
        ratio_values,
        ratio_stats,
    )

    print("\n生成完成:")
    print(f"  数据汇总 CSV : {csv_path}")
    print(f"  分析文本 TXT : {txt_path}")
    print(f"  第三谐波 SVG : {h3_svg_path}")
    print(f"  第五谐波 SVG : {h5_svg_path}")
    print(f"  五三比值 SVG : {ratio_svg_path}")


def run(folder_arg: str | None, file_arg: str | None, output_arg: str | None) -> None:
    selected_file, selected_dir = resolve_file_and_directory(file_arg, folder_arg)
    if selected_file is None and selected_dir is not None:
        selected_file = prompt_for_file(selected_dir, None)

    last_dir = selected_dir
    processed_count = 0

    while True:
        if selected_file is None:
            prompt_text = "请把 Spectra 文件拖到这里后回车"
            if processed_count > 0:
                prompt_text = "请拖入下一个 Spectra 文件，按 Ctrl+C 结束"
            if last_dir is not None:
                prompt_text += f" [当前目录: {last_dir}]"
            prompt_text += ": "
            selected_file, selected_dir = prompt_for_direct_file(
                None,
                base_dir=last_dir,
                prompt_text=prompt_text,
            )
        elif selected_dir is None:
            selected_dir = selected_file.parent

        try:
            process_selected_file(selected_file, selected_dir, output_arg)
            processed_count += 1
            last_dir = selected_dir
        except ValueError as exc:
            print(f"\n处理失败: {exc}")
            if selected_dir is not None:
                last_dir = selected_dir
        finally:
            selected_file = None
            selected_dir = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="持续接收 Spectra 文件，并生成第三、第五谐波变化图。"
    )
    parser.add_argument("--folder", help="可选，数据文件夹路径。")
    parser.add_argument("--file", help="目标 Spectra 文件路径，可直接拖入终端。")
    parser.add_argument("--output-dir", help="输出目录，默认自动生成 *_summary 文件夹。")
    args = parser.parse_args()

    try:
        run(args.folder, args.file, args.output_dir)
    except KeyboardInterrupt:
        print("\n已取消。")
    except EOFError:
        print("\n已结束。")
    except ValueError as exc:
        print(f"\n处理失败: {exc}")


if __name__ == "__main__":
    main()
