# exp_data

Utility scripts for analyzing experimental magnetic particle data from `Spectra` and `MH_Curve` text files.

## What this repo contains

- `exp_data`: CLI entrypoint for Spectra harmonic trend analysis.
- `exp_data_MH`: CLI entrypoint for MH loop metric analysis.
- `harmonic_plot_cli.py`: Spectra parser and report generator.
- `mh_curve_cli.py`: MH_Curve parser and report generator.
- `scripts/plot_harmonic_comparison.py`: cross-sample comparison plot helper.
- `data/`: raw and summarized experiment outputs.

## Quick start

Use Python 3.10+.

```bash
python3 exp_data run --folder data/20260417
python3 exp_data_MH run --folder data/20260417
```

Both tools auto-create a `*_summary` directory unless `--output-dir` is provided.

## Common commands

```bash
# Analyze one Spectra file directly
python3 exp_data run --file data/20260417/20_Spectra.txt

# Analyze one MH_Curve file directly
python3 exp_data_MH run --file data/20260417/水凝胶_MH_Curve.txt
```

## Project notes

- The repository is intentionally data-first and keeps generated summary artifacts under `data/*_summary/`.
- Local runtime/cache folders are ignored via `.gitignore`.
