# Model 2 evaluation report (what was measured; nothing estimated)

Raw JSON: `models/restoration/eval/{soil_models_report,soilgrids_check,restoration_eval}.json`. **Agreement with expert-rule labels measures consistency, not real-world restoration success; no observed restoration outcomes exist.**

## 1. Soil-property ML (observed labels, geographic validation)
Split: 5x5-degree spatial blocks, 8-fold CV on the training geography; held-out region = Levant + Arabian peninsula (lon 30-50, lat 20-38), never used for tuning/early stopping/calibration;
domain De Martonne <= 30 (semi-arid and drier). Metrics on log10(ECe) / log1p(ESP) ("t") and in physical units.

| Target | n train / held-out | Block-CV R2(t) (fold range) | CV RMSE (t) | Held-out region R2(t) [95 % block-bootstrap CI] | Held-out RMSE(t) | Held-out MAE (physical) | Global-median baseline R2(t) | 90 % conformal coverage CV / held-out |
|---|---|---|---|---|---|---|---|---|
| ECe (dS/m) | 9,264 / 138 (9 blocks) | 0.22 (0.14-0.40) | 0.57 (0.47-0.71) | 0.01 [-0.08, 0.27] | 0.63 | 6.4 dS/m | -0.90 | 0.901 / 0.870 |
| ESP (%) | 8,624 / 74 (6 blocks) | 0.18 (0.10-0.31) | 0.87 (0.74-0.95) | 0.01 [-0.99, 0.13] | 1.07 | 9.3 % | -1.13 | 0.901 / 0.905 |

- Held-out Jordan-only ECe (n=34): R2(t)=0.21, RMSE(t)=0.61. Arid subset (De Martonne<10, n=105): R2(t)=-0.26.
- Salinity-class (<2, 2-4, 4-8, 8-16, >16 dS/m) macro-F1: CV 0.21, held-out 0.27 (accuracy 0.46; within-one-class 0.75). ESP classes (<6, 6-15, >15): CV macro-F1 0.36, held-out 0.29.
- Ablation without SoilGrids covariates: ECe held-out R2(t) -0.19 (with: 0.01). SoilGrids was trained on WoSIS, so the "with" numbers are somewhat optimistic.
- **Interpretation:** the models beat a global-median predictor but explain almost none of the within-region variance on held-out geography; intervals are wide (90 % width about 2 log10 units for ECe).
  Inside Ma'an the salinity/sodicity map is a regional prior, not a field-level measurement.
- Optuna (16 trials) on block-CV RMSE; shallow trees, L2, feature/bagging fractions, early stopping inside each fold; no random row splits; duplicates removed (exact and cross-dataset within ~1 km and 10 %).

## 2. SoilGrids 2.0 vs measured WoSIS topsoil at arid sites (1 km aggregate, 5-15 cm vs 0-30 cm lab; leakage-optimistic)
| Property | region (n) | bias | RMSE | R2 |
|---|---|---|---|---|
| pH | held-out box, DM<30 (218) | -0.13 | 0.34 | 0.39 |
| SOC % | held-out box (195) | +0.28 | 0.55 | 0.00 |
| sand % | held-out box (220) | -1.4 | 10.8 | 0.71 |
| clay % | held-out box (220) | +0.4 | 9.2 | 0.70 |

These RMSE values are the 1-sigma input uncertainties of pH/SOC/texture in the Monte-Carlo.

## 3. Pipeline consistency on held-out geography (E2; consistency only)
104 measured WoSIS topsoil profiles in the held-out region: soil described (a) by measurement vs (b) only by covariates (held-out-region ECe model + SoilGrids); climate, ESP, CEC, CF, depth, slope fixed.
Observed-state classes 100 high / 2 moderate / 2 low; predicted-state 104 high. Accuracy 0.96, within-one-class 0.98, mean |score error| 0.078, Spearman of scores 0.04 (no ranking skill),
predicted 5-95 % interval contains the observed-state score for 94 % of profiles (mean width 0.26).
Reading: this test was run with the legacy uniform 8,000 m3/ha/yr allocation (since removed as the default), under which almost everything is "high", so it had little discriminating power; it shows insensitivity to soil-prediction error at that allocation, not skill.

## 4. Sensitivity (E3; 20,000 random Ma'an cells, 16x4 draws; LEGACY uniform water allocation)
_These runs used the explicit uniform what-if `water_cap` (the former default of 8,000 m3/ha/yr). The delivered outputs no longer use a uniform allocation: supply is each location's local renewable water (`docs/MODEL2_RESTORATION.md` section 5e). Re-run `eval/evaluate.py` for current figures._
| Change | mean score | class flip rate | Spearman vs baseline |
|---|---|---|---|
| baseline: reference water 8,000 m3/ha/yr | 0.877 | - | 1.00 |
| water 3,000 / 5,000 / 12,000 / 20,000 | 0.027 / 0.506 / 0.907 / 0.925 | 0.995 / 0.799 / 0.005 / 0.006 | 0.51 / 0.64 / 0.91 / 0.84 |
| class cuts -0.1 / +0.1 | 0.877 | 0.006 / 0.096 | 1.00 |
| RY success threshold 0.5 / 0.7 | 0.897 / 0.822 | 0.005 / 0.091 | 0.93 / 0.83 |
| ECe uncertainty x0.5; ECe x2; ESP x2 | 0.968; 0.775; 0.857 | 0.006; 0.144; 0.016 | 0.68; 0.84; 0.92 |
| max leaching depth ratio 0.7; gypsum cap 8 t/ha; ETo +20 % | 0.857; 0.813; 0.818 | 0.004; 0.086; 0.091 | 0.95; 0.81; 0.86 |

**Water is the decisive input**: under a uniform allocation below about 5,000 m3/ha/yr the same land flips to low/not feasible. That is why the delivered Model 2 uses geographically varying local renewable water instead of one number; read feasibility as "feasible with the water stated in the water block", not as proven availability.

## 5. ETo cross-check (E5)
Hargreaves (FAO-56 eq. 52) / TerraClimate Penman-Monteith over 4,032 region cells: mean 0.86 (5-95 %: 0.82-0.90); PM annual ETo median 1,932 mm. The engine uses PM with a +-10 % lognormal factor.

## 6. Pending / not done (not estimated)
Observed-analog check (existing irrigated cropland vs feasibility), AfSIS/iSDA domain-shift test, Hassani global-map benchmark at held-out points, own pH/SOC/texture models,
run on Model 1's real polygons (code path implemented, tested only with the stand-in), TerraClimate 30-year window, calibration of feasibility against real outcomes (impossible: none exist).
