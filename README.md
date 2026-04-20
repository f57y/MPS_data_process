# exp_data

用于分析 `Spectra` 与 `MH_Curve` 文本数据的实验处理脚本集合。

## 仓库内容

- `exp_data`：Spectra 谐波趋势分析的命令行入口。
- `exp_data_MH`：MH 回线指标分析的命令行入口。
- `harmonic_plot_cli.py`：Spectra 文件解析与报告生成脚本。
- `mh_curve_cli.py`：MH_Curve 文件解析与报告生成脚本。
- `scripts/plot_harmonic_comparison.py`：跨样本对比绘图辅助脚本。
- `data/`：原始实验数据与汇总分析结果。

## 环境要求

建议使用 Python 3.10 及以上版本。

## 数据存放说明

建议将实验原始数据放在 `data/` 下按日期分目录管理，例如：

```text
data/
  20260417/
    20_Spectra.txt
    水凝胶_Spectra.txt
    水凝胶_MH_Curve.txt
```

- `exp_data` 处理 `*Spectra*.txt`。
- `exp_data_MH` 处理 `*MH_Curve*.txt`。
- 输出默认写入同级的 `*_summary/` 目录。
  - 例如输入目录是 `data/20260417`，默认输出到 `data/20260417_summary`。
  - 如果输入目录本身已是 `*_summary`，则继续输出到该目录。
  - 也可用 `--output-dir` 显式指定输出目录。

## 快速启动命令

### 1) 交互模式（推荐）

```bash
python3 exp_data run
python3 exp_data_MH run
```

启动后按提示拖入目标文件（或文件夹）并回车。

### 2) 指定数据文件夹启动

```bash
python3 exp_data run --folder data/20260417
python3 exp_data_MH run --folder data/20260417
```

### 3) 直接指定单个文件启动

```bash
# 直接分析单个 Spectra 文件
python3 exp_data run --file data/20260417/20_Spectra.txt

# 直接分析单个 MH_Curve 文件
python3 exp_data_MH run --file data/20260417/水凝胶_MH_Curve.txt
```

## CLI 拖拽操作说明

1. 在终端运行命令（如 `python3 exp_data run`）。
2. 看到提示后，将文件管理器里的目标文件拖到终端窗口。
3. 终端会自动填入文件路径，按回车即可开始处理。
4. 本次处理完成后，可继续拖入下一个文件；按 `Ctrl+C` 结束程序。

补充说明：

- 也可以拖入整个文件夹，程序会列出候选 `.txt` 文件，让你输入序号或文件名选择。
- 带空格或中文的路径可直接拖入，程序会自动解析。

## 项目说明

- 仓库以“数据与结果留存”为主，生成的汇总文件统一放在 `data/*_summary/` 下。
- 本地运行缓存与环境目录通过 `.gitignore` 自动忽略。
