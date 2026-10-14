# Error analysis

This folder holds worksheets from real eval runs. It is empty in the reference repository on purpose: error
analysis means reading *your* agent's conversations, and the categories you find are the most valuable output of
Lab 3. Run the suite, generate a worksheet, read every transcript, and keep the tallied table in
`ERROR_ANALYSIS.md` next to the date and model you ran.

```bash
uv run python -m evals.run --suite pr --trials 1 --save runs/analysis.json
uv run python -m evals.error_analysis worksheet runs/analysis.json --n 60
uv run python -m evals.error_analysis tally evals/analysis/worksheet.md
```
