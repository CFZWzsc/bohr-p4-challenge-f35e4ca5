# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-f35e4ca5` (track: `literature-reading`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable entry point and all supporting scripts. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `figure-axis-calibrator`
- Summary: Use when a scientific figure must be read into numbers — calibrate axes from tick marks (linear or log), convert pixel positions to data values with units and precision, and emit /app/output/result.json preserving case_id and every output_contract field.

## Contents

| File |
|------|
| `SKILL.md` |
| `scripts/run_skill.py` |
| `README.md` |

## How to run

```bash
python scripts/run_skill.py --case /input/case.json --output /app/output/result.json
```

The entry point is `SKILL.md`; input/output contracts, error handling and a minimal
usage example are documented there.

## Notes

- Pure Python standard library; no network access required.
- The result JSON keeps the input case id, the main results, per-item evidence,
  a run status and an uncertainty section.
