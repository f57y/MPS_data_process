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


POINTS_PER_MEASUREMENT = 201
HIGH_FIELD_FRACTION = 0.95

MS_COLOR = "#1d70b8"
MR_COLOR = "#d95f02"
HC_COLOR = "#2f855a"
AREA_COLOR = "#8b5cf6"
LOOP_START_COLOR = "#1d70b8"
LOOP_END_COLOR = "#d95f02"
TREND_COLOR = "#5f6368"
GRID_COLOR = "#d9dfe8"
TEXT_COLOR = "#1f2933"
BG_COLOR = "#ffffff"


@dataclass
class MetricStats:
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
    preferred = sorted(directory.glob("*MH_Curve*.txt"))
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
    prompt_text: str = "请把 MH_Curve 文件拖到这里后回车: ",
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


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def linear_fit(values: list[float]) -> tuple[float, float]:
    if len(values) == 1:
        return 0.0, values[0]

    x_values = [float(index) for index in range(1, len(values) + 1)]
    x_mean = mean(x_values)
    y_mean = mean(values)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    slope = numerator / denominator if denominator else 0.0
    intercept = y_mean - slope * x_mean
    return slope, intercept


def calc_stats(values: list[float]) -> MetricStats:
    mean_value = mean(values)
    std_value = st.stdev(values) if len(values) > 1 else 0.0
    cv_percent = std_value / mean_value * 100.0 if mean_value else float("nan")
    first_value = values[0]
    last_value = values[-1]
    slope, intercept = linear_fit(values)
    drift_value = last_value - first_value
    drift_percent_of_mean = drift_value / mean_value * 100.0 if mean_value else float("nan")
    return MetricStats(
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


def interpolate_y_at_target_x(
    x_values: list[float],
    y_values: list[float],
    target_x: float = 0.0,
) -> float:
    exact = [y for x, y in zip(x_values, y_values) if abs(x - target_x) < 1e-12]
    if exact:
        return mean(exact)

    for index in range(len(x_values) - 1):
        x1 = x_values[index]
        x2 = x_values[index + 1]
        if (x1 - target_x) * (x2 - target_x) > 0:
            continue

        y1 = y_values[index]
        y2 = y_values[index + 1]
        if abs(x2 - x1) < 1e-12:
            return mean([y1, y2])
        ratio = (target_x - x1) / (x2 - x1)
        return y1 + ratio * (y2 - y1)

    return float("nan")


def interpolate_x_at_target_y(
    x_values: list[float],
    y_values: list[float],
    target_y: float = 0.0,
) -> float:
    exact = [x for x, y in zip(x_values, y_values) if abs(y - target_y) < 1e-12]
    if exact:
        return mean(exact)

    for index in range(len(y_values) - 1):
        y1 = y_values[index]
        y2 = y_values[index + 1]
        if (y1 - target_y) * (y2 - target_y) > 0:
            continue

        x1 = x_values[index]
        x2 = x_values[index + 1]
        if abs(y2 - y1) < 1e-12:
            return mean([x1, x2])
        ratio = (target_y - y1) / (y2 - y1)
        return x1 + ratio * (x2 - x1)

    return float("nan")


def integrate_loop_area(fields: list[float], magnetizations: list[float]) -> float:
    area = 0.0
    for h1, h2, m1, m2 in zip(fields, fields[1:], magnetizations, magnetizations[1:]):
        area += (m1 + m2) * (h2 - h1) * 0.5

    if abs(fields[0] - fields[-1]) > 1e-12 or abs(magnetizations[0] - magnetizations[-1]) > 1e-12:
        area += (
            (magnetizations[-1] + magnetizations[0])
            * (fields[0] - fields[-1])
            * 0.5
        )

    return abs(area)


def extract_loop_metrics(
    loop_rows: list[tuple[float, float, float]],
    measurement_index: int,
) -> dict[str, float | int]:
    frequencies = [row[0] for row in loop_rows]
    fields = [row[1] for row in loop_rows]
    magnetizations = [row[2] for row in loop_rows]

    max_index = max(range(len(fields)), key=lambda index: fields[index])
    min_index = min(range(max_index, len(fields)), key=lambda index: fields[index])
    if min_index <= max_index:
        raise ValueError(
            f"第 {measurement_index} 次测量的扫描顺序异常，无法识别完整回线。"
        )

    up_branch_fields = fields[: max_index + 1]
    up_branch_magnetizations = magnetizations[: max_index + 1]
    down_branch_fields = fields[max_index : min_index + 1]
    down_branch_magnetizations = magnetizations[max_index : min_index + 1]
    return_branch_fields = fields[min_index:]
    return_branch_magnetizations = magnetizations[min_index:]

    field_max = max(fields)
    field_min = min(fields)
    positive_high_m = [
        m for h, m in zip(fields, magnetizations) if h >= field_max * HIGH_FIELD_FRACTION
    ]
    negative_high_m = [
        m for h, m in zip(fields, magnetizations) if h <= field_min * HIGH_FIELD_FRACTION
    ]
    if not positive_high_m or not negative_high_m:
        raise ValueError(
            f"第 {measurement_index} 次测量无法识别高场平台，Ms 计算失败。"
        )

    ms_positive = mean(positive_high_m)
    ms_negative = mean(negative_high_m)
    ms = (ms_positive - ms_negative) * 0.5

    mr_positive = interpolate_y_at_target_x(down_branch_fields, down_branch_magnetizations)
    mr_negative = interpolate_y_at_target_x(return_branch_fields, return_branch_magnetizations)
    if math.isnan(mr_negative):
        mr_negative = interpolate_y_at_target_x(up_branch_fields, up_branch_magnetizations)
    mr = (mr_positive - mr_negative) * 0.5

    hc_positive = interpolate_x_at_target_y(up_branch_fields, up_branch_magnetizations)
    hc_negative = interpolate_x_at_target_y(down_branch_fields, down_branch_magnetizations)
    if math.isnan(hc_positive):
        hc_positive = interpolate_x_at_target_y(return_branch_fields, return_branch_magnetizations)
    hc = (hc_positive - hc_negative) * 0.5

    loop_area = integrate_loop_area(fields, magnetizations)
    mr_over_ms = mr / ms if abs(ms) > 1e-12 else float("nan")
    saturation_offset = (ms_positive + ms_negative) * 0.5
    coercive_offset = (hc_positive + hc_negative) * 0.5
    remanence_offset = (mr_positive + mr_negative) * 0.5

    if any(math.isnan(value) for value in [mr_positive, mr_negative, hc_positive, hc_negative]):
        raise ValueError(
            f"第 {measurement_index} 次测量无法可靠插值得到 Mr 或 Hc。"
        )

    return {
        "measurement_index": measurement_index,
        "frequency_hz": mean(frequencies),
        "point_count": len(loop_rows),
        "field_min_mt": field_min,
        "field_max_mt": field_max,
        "magnetization_min": min(magnetizations),
        "magnetization_max": max(magnetizations),
        "ms_positive": ms_positive,
        "ms_negative": ms_negative,
        "ms": ms,
        "mr_positive": mr_positive,
        "mr_negative": mr_negative,
        "mr": mr,
        "hc_positive_mt": hc_positive,
        "hc_negative_mt": hc_negative,
        "hc_mt": hc,
        "loop_area": loop_area,
        "mr_over_ms": mr_over_ms,
        "saturation_offset": saturation_offset,
        "remanence_offset": remanence_offset,
        "coercive_offset_mt": coercive_offset,
    }


def parse_mh_file(
    path: Path,
    points_per_measurement: int = POINTS_PER_MEASUREMENT,
) -> tuple[list[dict[str, float | int]], list[list[tuple[float, float, float]]]]:
    raw_rows: list[tuple[float, float, float]] = []
    with path.open("r", encoding="utf-8") as infile:
        for index, line in enumerate(infile, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            values = [float(part) for part in stripped.split()]
            if len(values) < 3:
                raise ValueError(
                    f"{path.name} 看起来不是 MH_Curve 文件: 第 {index} 行只有 {len(values)} 列。"
                )
            raw_rows.append((values[0], values[1], values[2]))

    if not raw_rows:
        raise ValueError(f"{path.name} 没有可读取的数据行。")
    if len(raw_rows) % points_per_measurement != 0:
        raise ValueError(
            f"{path.name} 的有效数据行数为 {len(raw_rows)}，不能被 {points_per_measurement} 整除。"
        )

    loop_count = len(raw_rows) // points_per_measurement
    loops = [
        raw_rows[index * points_per_measurement : (index + 1) * points_per_measurement]
        for index in range(loop_count)
    ]
    metrics = [
        extract_loop_metrics(loop_rows, measurement_index=index + 1)
        for index, loop_rows in enumerate(loops)
    ]
    return metrics, loops


def write_combined_csv(path: Path, rows: list[dict[str, float | int]]) -> None:
    fieldnames = [
        "measurement_index",
        "frequency_hz",
        "point_count",
        "field_min_mt",
        "field_max_mt",
        "magnetization_min",
        "magnetization_max",
        "ms_positive",
        "ms_negative",
        "ms",
        "mr_positive",
        "mr_negative",
        "mr",
        "hc_positive_mt",
        "hc_negative_mt",
        "hc_mt",
        "loop_area",
        "mr_over_ms",
        "saturation_offset",
        "remanence_offset",
        "coercive_offset_mt",
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
    points_per_measurement: int,
    loop_count: int,
    ms_stats: MetricStats,
    mr_stats: MetricStats,
    hc_stats: MetricStats,
    area_stats: MetricStats,
) -> None:
    lines = [
        f"{source_file.stem} {freq_label} MH Curve Analysis",
        f"source_file\t{source_file}",
        f"output_dir\t{output_dir}",
        f"points_per_measurement\t{points_per_measurement}",
        f"measurement_count\t{loop_count}",
        f"definition_ms\taverage(|high-field magnetization|) with {HIGH_FIELD_FRACTION:.0%} field threshold",
        "definition_mr\t(Mr+ - Mr-) / 2, interpolated at H = 0 on descending/return branches",
        "definition_hc\t(Hc+ - Hc-) / 2, interpolated at M = 0 on ascending/descending branches",
        "definition_loop_area\tabsolute value of ∮M dH",
        "",
        "[ms]",
        f"count\t{ms_stats.count}",
        f"min\t{ms_stats.minimum:.12f}",
        f"max\t{ms_stats.maximum:.12f}",
        f"mean\t{ms_stats.mean:.12f}",
        f"std\t{ms_stats.std:.12f}",
        f"cv_percent\t{ms_stats.cv_percent:.6f}",
        f"linear_slope_per_measurement\t{ms_stats.slope_per_measurement:.12e}",
        f"first_value\t{ms_stats.first_value:.12f}",
        f"last_value\t{ms_stats.last_value:.12f}",
        f"drift_last_minus_first\t{ms_stats.drift_value:.12f}",
        f"drift_percent_of_mean\t{ms_stats.drift_percent_of_mean:.6f}",
        "",
        "[mr]",
        f"count\t{mr_stats.count}",
        f"min\t{mr_stats.minimum:.12f}",
        f"max\t{mr_stats.maximum:.12f}",
        f"mean\t{mr_stats.mean:.12f}",
        f"std\t{mr_stats.std:.12f}",
        f"cv_percent\t{mr_stats.cv_percent:.6f}",
        f"linear_slope_per_measurement\t{mr_stats.slope_per_measurement:.12e}",
        f"first_value\t{mr_stats.first_value:.12f}",
        f"last_value\t{mr_stats.last_value:.12f}",
        f"drift_last_minus_first\t{mr_stats.drift_value:.12f}",
        f"drift_percent_of_mean\t{mr_stats.drift_percent_of_mean:.6f}",
        "",
        "[hc]",
        f"count\t{hc_stats.count}",
        f"min\t{hc_stats.minimum:.12f}",
        f"max\t{hc_stats.maximum:.12f}",
        f"mean\t{hc_stats.mean:.12f}",
        f"std\t{hc_stats.std:.12f}",
        f"cv_percent\t{hc_stats.cv_percent:.6f}",
        f"linear_slope_per_measurement\t{hc_stats.slope_per_measurement:.12e}",
        f"first_value\t{hc_stats.first_value:.12f}",
        f"last_value\t{hc_stats.last_value:.12f}",
        f"drift_last_minus_first\t{hc_stats.drift_value:.12f}",
        f"drift_percent_of_mean\t{hc_stats.drift_percent_of_mean:.6f}",
        "",
        "[loop_area]",
        f"count\t{area_stats.count}",
        f"min\t{area_stats.minimum:.12f}",
        f"max\t{area_stats.maximum:.12f}",
        f"mean\t{area_stats.mean:.12f}",
        f"std\t{area_stats.std:.12f}",
        f"cv_percent\t{area_stats.cv_percent:.6f}",
        f"linear_slope_per_measurement\t{area_stats.slope_per_measurement:.12e}",
        f"first_value\t{area_stats.first_value:.12f}",
        f"last_value\t{area_stats.last_value:.12f}",
        f"drift_last_minus_first\t{area_stats.drift_value:.12f}",
        f"drift_percent_of_mean\t{area_stats.drift_percent_of_mean:.6f}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def fmt_float(value: float) -> str:
    return f"{value:.6f}"


def build_metric_svg_plot(
    path: Path,
    file_name: str,
    freq_label: str,
    metric_label: str,
    y_axis_label: str,
    color: str,
    measurements: list[int],
    values: list[float],
    stats: MetricStats,
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

    y_min = min(values)
    y_max = max(values)
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
        for x, y in zip(measurements, values)
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
        f'fill="{TEXT_COLOR}">{html.escape(metric_label)} Trend</text>',
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

    for x_value, y_value in zip(measurements, values):
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
            f'fill="{TEXT_COLOR}">{html.escape(y_axis_label)}</text>',
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
            f'fill="{TEXT_COLOR}">Measured value</text>',
            f'<line x1="{stats_x}" y1="{legend_y + 32}" x2="{stats_x + 32}" y2="{legend_y + 32}" stroke="{TREND_COLOR}" stroke-width="3" stroke-dasharray="8 6"/>',
            f'<text x="{stats_x + 44}" y="{legend_y + 38}" font-size="15" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Linear trend</text>',
            f'<text x="{width - 22}" y="{height - 18}" text-anchor="end" font-size="12" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="#6b7785">Generated by mh_curve_cli.py</text>',
            "</svg>",
        ]
    )

    path.write_text("\n".join(svg_lines), encoding="utf-8")


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def blend_colors(start: str, end: str, ratio: float) -> str:
    start_rgb = hex_to_rgb(start)
    end_rgb = hex_to_rgb(end)
    blended = tuple(
        round(start_value + (end_value - start_value) * ratio)
        for start_value, end_value in zip(start_rgb, end_rgb)
    )
    return rgb_to_hex(blended)


def build_loop_evolution_svg(
    path: Path,
    file_name: str,
    freq_label: str,
    loops: list[list[tuple[float, float, float]]],
) -> None:
    width = 1500
    height = 820
    left = 100
    top = 100
    plot_width = 950
    plot_height = 600
    plot_right = left + plot_width
    plot_bottom = top + plot_height
    sidebar_x = plot_right + 40

    all_fields = [row[1] for loop in loops for row in loop]
    all_magnetizations = [row[2] for loop in loops for row in loop]
    x_min = min(all_fields)
    x_max = max(all_fields)
    y_min = min(all_magnetizations)
    y_max = max(all_magnetizations)
    x_padding = (x_max - x_min) * 0.06 if x_max != x_min else 1.0
    y_padding = (y_max - y_min) * 0.08 if y_max != y_min else 1.0
    x_min -= x_padding
    x_max += x_padding
    y_min -= y_padding
    y_max += y_padding

    def scale_x(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_width

    def scale_y(value: float) -> float:
        return plot_bottom - (value - y_min) / (y_max - y_min) * plot_height

    x_ticks = 7
    y_ticks = 7
    highlighted_indices = sorted({0, max(len(loops) // 2, 0), len(loops) - 1})
    highlighted_colors = ["#0f4c81", "#2f855a", "#b54708"]

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<linearGradient id="loopGradient" x1="0%" y1="0%" x2="100%" y2="0%">',
        f'<stop offset="0%" stop-color="{LOOP_START_COLOR}"/>',
        f'<stop offset="100%" stop-color="{LOOP_END_COLOR}"/>',
        "</linearGradient>",
        "</defs>",
        f'<rect width="{width}" height="{height}" fill="{BG_COLOR}"/>',
        '<text x="100" y="56" font-size="28" font-weight="700" '
        'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
        f'fill="{TEXT_COLOR}">MH Loop Evolution</text>',
        '<text x="100" y="84" font-size="16" '
        'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
        f'fill="{TEXT_COLOR}">{html.escape(file_name)} | {html.escape(freq_label)}</text>',
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#fbfcfe" stroke="#c7d0db"/>',
    ]

    for index in range(x_ticks):
        ratio = index / (x_ticks - 1)
        x_value = x_min + ratio * (x_max - x_min)
        x_pos = scale_x(x_value)
        svg_lines.append(
            f'<line x1="{x_pos:.2f}" y1="{top}" x2="{x_pos:.2f}" y2="{plot_bottom}" stroke="{GRID_COLOR}" stroke-width="1"/>'
        )
        svg_lines.append(
            f'<text x="{x_pos:.2f}" y="{plot_bottom + 30}" text-anchor="middle" font-size="14" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">{x_value:.2f}</text>'
        )

    for index in range(y_ticks):
        ratio = index / (y_ticks - 1)
        y_value = y_max - ratio * (y_max - y_min)
        y_pos = scale_y(y_value)
        svg_lines.append(
            f'<line x1="{left}" y1="{y_pos:.2f}" x2="{plot_right}" y2="{y_pos:.2f}" stroke="{GRID_COLOR}" stroke-width="1"/>'
        )
        svg_lines.append(
            f'<text x="{left - 12}" y="{y_pos + 5:.2f}" text-anchor="end" font-size="14" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">{y_value:.2f}</text>'
        )

    zero_x = scale_x(0.0)
    zero_y = scale_y(0.0)
    svg_lines.extend(
        [
            f'<line x1="{left}" y1="{zero_y:.2f}" x2="{plot_right}" y2="{zero_y:.2f}" stroke="#7b8794" stroke-width="1.6"/>',
            f'<line x1="{zero_x:.2f}" y1="{top}" x2="{zero_x:.2f}" y2="{plot_bottom}" stroke="#7b8794" stroke-width="1.6"/>',
        ]
    )

    for loop_index, loop in enumerate(loops):
        ratio = loop_index / max(len(loops) - 1, 1)
        color = blend_colors(LOOP_START_COLOR, LOOP_END_COLOR, ratio)
        points = " ".join(
            f"{scale_x(field):.2f},{scale_y(magnetization):.2f}"
            for _, field, magnetization in loop
        )
        svg_lines.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" opacity="0.45" points="{points}"/>'
        )

    for highlight_order, loop_index in enumerate(highlighted_indices):
        loop = loops[loop_index]
        color = highlighted_colors[min(highlight_order, len(highlighted_colors) - 1)]
        points = " ".join(
            f"{scale_x(field):.2f},{scale_y(magnetization):.2f}"
            for _, field, magnetization in loop
        )
        svg_lines.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="3.2" opacity="0.95" points="{points}"/>'
        )

    svg_lines.extend(
        [
            f'<text x="{left + plot_width / 2:.2f}" y="{height - 28}" text-anchor="middle" font-size="18" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Magnetic Field, H (mT)</text>',
            f'<text x="36" y="{top + plot_height / 2:.2f}" transform="rotate(-90 36 {top + plot_height / 2:.2f})" '
            'text-anchor="middle" font-size="18" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Magnetization, M (a.u.)</text>',
            f'<rect x="{sidebar_x}" y="148" width="320" height="320" rx="14" fill="#f6f8fb" stroke="#d7dee7"/>',
            f'<text x="{sidebar_x + 20}" y="184" font-size="20" font-weight="700" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Loop Overview</text>',
            f'<text x="{sidebar_x + 20}" y="220" font-size="16" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Measurements: {len(loops)}</text>',
            f'<text x="{sidebar_x + 20}" y="248" font-size="16" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Points / loop: {len(loops[0])}</text>',
            f'<text x="{sidebar_x + 20}" y="276" font-size="16" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Field span: {min(all_fields):.2f} to {max(all_fields):.2f} mT</text>',
            f'<text x="{sidebar_x + 20}" y="304" font-size="16" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">M span: {min(all_magnetizations):.2f} to {max(all_magnetizations):.2f}</text>',
            f'<text x="{sidebar_x + 20}" y="342" font-size="15" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Thin lines: all measurements</text>',
            f'<text x="{sidebar_x + 20}" y="370" font-size="15" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Bold lines: representative loops</text>',
            f'<rect x="{sidebar_x + 20}" y="402" width="190" height="16" fill="url(#loopGradient)" rx="8"/>',
            f'<text x="{sidebar_x + 20}" y="438" font-size="14" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Measurement 1</text>',
            f'<text x="{sidebar_x + 210}" y="438" text-anchor="end" font-size="14" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">Measurement {len(loops)}</text>',
        ]
    )

    legend_y = 516
    legend_labels = [
        f"Measurement {highlighted_indices[0] + 1}",
        f"Measurement {highlighted_indices[1] + 1}",
        f"Measurement {highlighted_indices[2] + 1}",
    ]
    for offset, (color, label) in enumerate(zip(highlighted_colors, legend_labels)):
        y = legend_y + offset * 34
        svg_lines.append(
            f'<line x1="{sidebar_x + 20}" y1="{y}" x2="{sidebar_x + 52}" y2="{y}" stroke="{color}" stroke-width="4"/>'
        )
        svg_lines.append(
            f'<text x="{sidebar_x + 64}" y="{y + 6}" font-size="15" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="{TEXT_COLOR}">{html.escape(label)}</text>'
        )

    svg_lines.extend(
        [
            f'<text x="{width - 22}" y="{height - 18}" text-anchor="end" font-size="12" '
            'font-family="Noto Sans SC, Microsoft YaHei, sans-serif" '
            f'fill="#6b7785">Generated by mh_curve_cli.py</text>',
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
    rows, loops = parse_mh_file(selected_file)
    measurements = [int(row["measurement_index"]) for row in rows]
    ms_values = [float(row["ms"]) for row in rows]
    mr_values = [float(row["mr"]) for row in rows]
    hc_values = [float(row["hc_mt"]) for row in rows]
    area_values = [float(row["loop_area"]) for row in rows]

    ms_stats = calc_stats(ms_values)
    mr_stats = calc_stats(mr_values)
    hc_stats = calc_stats(hc_values)
    area_stats = calc_stats(area_values)
    freq_label = frequency_tag(rows)

    csv_path = output_dir / f"{selected_file.stem}_metrics_{freq_label}.csv"
    txt_path = output_dir / f"{selected_file.stem}_analysis_{freq_label}.txt"
    ms_svg_path = output_dir / f"{selected_file.stem}_ms_trend_{freq_label}.svg"
    mr_svg_path = output_dir / f"{selected_file.stem}_mr_trend_{freq_label}.svg"
    hc_svg_path = output_dir / f"{selected_file.stem}_hc_trend_{freq_label}.svg"
    area_svg_path = output_dir / f"{selected_file.stem}_loop_area_trend_{freq_label}.svg"
    loop_svg_path = output_dir / f"{selected_file.stem}_loop_evolution_{freq_label}.svg"

    write_combined_csv(csv_path, rows)
    write_analysis_txt(
        txt_path,
        selected_file,
        output_dir,
        freq_label,
        POINTS_PER_MEASUREMENT,
        len(rows),
        ms_stats,
        mr_stats,
        hc_stats,
        area_stats,
    )
    build_metric_svg_plot(
        ms_svg_path,
        selected_file.name,
        freq_label,
        "Ms",
        "Ms (a.u.)",
        MS_COLOR,
        measurements,
        ms_values,
        ms_stats,
    )
    build_metric_svg_plot(
        mr_svg_path,
        selected_file.name,
        freq_label,
        "Mr",
        "Mr (a.u.)",
        MR_COLOR,
        measurements,
        mr_values,
        mr_stats,
    )
    build_metric_svg_plot(
        hc_svg_path,
        selected_file.name,
        freq_label,
        "Hc",
        "Hc (mT)",
        HC_COLOR,
        measurements,
        hc_values,
        hc_stats,
    )
    build_metric_svg_plot(
        area_svg_path,
        selected_file.name,
        freq_label,
        "Loop Area",
        "Loop Area (a.u. * mT)",
        AREA_COLOR,
        measurements,
        area_values,
        area_stats,
    )
    build_loop_evolution_svg(loop_svg_path, selected_file.name, freq_label, loops)

    print("\n生成完成:")
    print(f"  指标汇总 CSV : {csv_path}")
    print(f"  分析文本 TXT : {txt_path}")
    print(f"  Ms 趋势 SVG : {ms_svg_path}")
    print(f"  Mr 趋势 SVG : {mr_svg_path}")
    print(f"  Hc 趋势 SVG : {hc_svg_path}")
    print(f"  面积趋势 SVG : {area_svg_path}")
    print(f"  回线演化 SVG : {loop_svg_path}")


def run(folder_arg: str | None, file_arg: str | None, output_arg: str | None) -> None:
    selected_file, selected_dir = resolve_file_and_directory(file_arg, folder_arg)
    if selected_file is None and selected_dir is not None:
        selected_file = prompt_for_file(selected_dir, None)

    last_dir = selected_dir
    processed_count = 0

    while True:
        if selected_file is None:
            prompt_text = "请把 MH_Curve 文件拖到这里后回车"
            if processed_count > 0:
                prompt_text = "请拖入下一个 MH_Curve 文件，按 Ctrl+C 结束"
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
        description="持续接收 MH_Curve 文件，并分析 Ms、Mr、Hc 与磁滞回线演化。"
    )
    parser.add_argument("--folder", help="可选，数据文件夹路径。")
    parser.add_argument("--file", help="目标 MH_Curve 文件路径，可直接拖入终端。")
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
