# Decision: prompt variants and calibration maps for LLM/Jev routers (pre-registration input)

Date: 2026-10-01. Owner: study lead. Status: decided before any test_v2 call.

1. **Prompt variants.** Apply `config/prompt_selection.yaml` as selected by the pre-declared
   one-SE rule: Sonnet 5, Haiku 4.5 and Jev use P0 on both tracks (canonical = tuned). The
   `raw_best` argmax alternatives (Sonnet/Haiku P0+P4, Jev P0+P6c) are NOT applied; they are
   reported as dev-only sensitivity. Jev P0+P6c is additionally reported as a cost variant in an
   exploratory routing-only run (labelled exploratory, not part of H1-H3).
2. **Calibration maps.** A map is applied to a (model, track, stage) only when its cross-fitted
   ECE on dev is lower than the raw ECE (`ece_cal < ece_raw` in prompt_selection.yaml).
   Otherwise the raw confidence is used. Same rule for every strategy. Cascade thresholds are then
   calibrated on a dev shadow run with these final configs (D5).
3. **Qwen3-8B (E6b)** follows the same selection procedure on dev before freezing; its result is
   appended to prompt_selection.yaml with select_prompts.py and the canonical rule is recomputed
   across all four LLM-type routers.
