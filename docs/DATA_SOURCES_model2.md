# Model 2 (restoration potential) - data sources and verification log

Convention: **Used** = enters a trained model, the stack or an evaluation. **Verified** lists only what was actually opened/measured by the model2 agent.
Raw data live in `$GREEN_NOVA_DATA/raw/<dataset>` (outside the repository). No credentials, tokens or accounts were created.

## 0. Headline finding: no before/after restoration dataset
No dataset with paired degraded-state / post-restoration soil outcomes was found in the sources below. Kaggle datasets that mention "restoration" have no provenance
(see section 9) or concern microbial OTU tables of reclaimed mines. **Restoration outcomes in Model 2 are therefore simulated** from documented relationships; nothing was
manufactured as ground truth. Evidence classes: observed / ml_predicted / expert_rule / simulated.

## 1. Africa Soil Property Prediction Challenge (Kaggle) - GATED, NOT ACCESSED
- URL: https://www.kaggle.com/competitions/afsis-soil-properties/data . Public data page read (signed-out): `train.csv` 1,158 rows, `test.csv` 728 rows, `sample_submission.csv`; 3 files, 21.7 MB zip;
  targets SOC, pH, Ca (Mehlich-3), P (Mehlich-3), Sand; 3,578 MIR absorbance columns + MODIS/SRTM/TRMM covariates; licence text "Subject to Competition Rules".
- Data are *monotonically transformed* (negative values, not physical units), covariates are mean-centred/scaled, **no coordinates**, no EC/salinity, depth only topsoil/subsoil; the sampling design excludes true deserts
  (Sentinel Landscapes across non-desert Africa). Download requires accepting the competition rules: **not accepted** (owner authorisation for AfSIS was later withdrawn by the coordinator).
- Judgement for Jordan: low value. No MIR spectra exist for Ma'an, sub-Saharan non-desert sites are a large domain shift, targets lack salinity/sodicity. Role: none (blocker recorded, not needed).

## 2. AfSIS Phase I wet chemistry - public AWS mirror (downloaded, not used in final models)
- `s3://afsis/2009-2013/` (anonymous), registry https://registry.opendata.aws/afsis/ . Downloaded to `raw\afsis\aws_mirror`: `georeferences.csv` 230,718 B (SSN, lat/lon, cluster/plot, depth top/sub, country),
  `Wet_Chemistry_CROPNUTS.csv` 238,540 B (EC, pH, Mehlich-3), `Wet_Chemistry_ICRAF.csv` 694,127 B (texture, total C/N), `Wet_Chemistry_RRES.csv` 222,668 B, README, LICENSE.txt (ODC-By text; the registry page says ODbL 1.0 - inconsistent, unresolved).
- Verified: file listing, headers, README. Not verified: sample counts after joins, EC method (extract ratio). **Used: no** (time cut; planned only as a domain-shift side test).
- iSDA "open-soil-data" repo (https://github.com/iSDA-Africa/open-soil-data, `iSDA_soil_data.csv` 7.0 MB, 49,224 rows): 47,068 rows are `afsis_spectral` = MIR-PREDICTED values, only 2,157 are wet chemistry; OSF licence CC BY 4.0. Not used.

## 3. WoSIS 2023-12 snapshot (ISRIC) - USED (ECe labels, SoilGrids check)
- https://files.isric.org/public/wosis_snapshot/WoSIS_2023_December.zip ; 456,066,475 B; **sha256 3115c6be84613dc960c600768a9999dd6d6ad5207017065196b7e356d3c50f3a = published checksum (verified)**. DOI 10.17027/isric-wdcsoils-20231130; paper Batjes et al. 2024 ESSD 16:4735 (landing page read).
- Per-record licences (US public domain / CC BY 3.0 / CC BY 4.0 / CC BY-NC). **CC BY-NC rows (e.g. Mexico INEGI) are excluded from training** (commercial-use risk). ELCOSP (saturated-paste EC = ECe): 22,052 profiles / 85,020 layers; Jordan: 191 ECe layer records (US-NCSS).
- Derived (not redistributed): `cache\model2\wosis_topsoil.csv.gz` (194,258 profiles after duplicate removal; 17,534 with ECe). Positional uncertainty ~100 m for 86 % of profiles; sampling is purposive, not probabilistic.

## 4. Hassani, Azapagic & Shokri 2020 (Mendeley Data) - USED (training points only)
- https://data.mendeley.com/datasets/v9mgbmtnf2/1 ; DOI 10.17632/v9mgbmtnf2.1 ; CC BY 4.0 ; 15 files, 4.0 GB total (public API listing read). Downloaded: `READ_ME.pdf` (read), `ECe_input_training_data.zip` 2,581,945 B (43,602 measured ECe records),
  `ESP_input_training_data.zip` 9,585,575 B (207,048 records with exchangeable Na and CEC -> ESP = ExNa/CEC x 100). Aggregated to 14,112 ECe and 30,204 ESP locations (0-30 cm) after duplicate removal against WoSIS.
- The global maps (mean ECe/ESP ~600 MB each) were NOT used (partial download only). README: the "SD" maps are the *temporal* SD of annual predictions, not model uncertainty.

## 5. SoilGrids (ISRIC) - USED (third-party ml_predicted layers)
- 2.0 aggregated 1 km, 5-15 cm mean (phh2o 79,096,499 B; clay 192,320,598 B; sand 199,088,292 B; soc 213,203,577 B) from https://files.isric.org/soilgrids/latest/data_aggregated/1000m/ - ECe/ESP model covariates and the arid-site error check. CC BY 4.0 (ISRIC statement, as recorded in the shared manifest).
- 2.0 250 m layers (phh2o, soc, sand, silt, clay, cfvo, cec, bdod; 0-5/5-15/15-30 cm) for Ma'an were fetched by model1 into the shared cache (`manifest.json`); Model 2 only reads them.
- 2017 BDRICM depth to bedrock (https://files.isric.org/soilgrids/former/2017-03-10/data/BDRICM_M_250m_ll.tif, 1,443,918,663 B global; window read for Ma'an; values capped at 200 cm and ~all 200 in Ma'an = uninformative). **Licence of the 2017 product not re-verified.**
- Measured quality at arid WoSIS sites: `eval/soilgrids_check.json` (e.g. test region n=218: pH RMSE 0.34; SOC RMSE 0.55 % with R2~0; sand RMSE 10.8 %; clay RMSE 9.2 %). SoilGrids was trained on WoSIS -> optimistic.

## 6. Climate / terrain - USED
- WorldClim 2.1 (https://geodata.ucdavis.edu/climate/worldclim/2_1/base/): `wc2.1_5m_bio.zip` 179,563,774 B, `wc2.1_30s_elev.zip` 338,188,707 B (global ECe/ESP covariates). Licence not re-verified in this session.
- TerraClimate monthly ppt/pet/tmax/tmin: model1's cached raw arrays 2011-2020 (Planetary Computer zarr); **10-year window** used for climatology and the 2-in-3-years design rainfall (a 30-year record would be better).
- Copernicus GLO-30 DEM (model1 cache, `dem_cop30`) -> 50 m slope -> 250 m. Boundary: geoBoundaries gbOpen JOR ADM1 (CC BY 2.5, 2006 vintage), canonical copy by model1.

## 7. Authoritative documents used for thresholds/equations (read in full text; see `models/restoration/knowledge/sources.py`)
FAO IDP 29 rev.1 (https://www.fao.org/4/t0234e/t0234e00.htm), FAO IDP 56 (https://www.fao.org/4/x0490e/x0490e00.htm), FAO Soils Bulletin 55 (https://www.fao.org/3/x5648e/x5648e00.htm),
FAO Soils Bulletin 39 (https://www.fao.org/4/x5871e/x5871e00.htm), FAO water-harvesting manual AGL/MISC/17/91 (https://www.fao.org/3/u3160e/u3160e00.htm), SWAT+ documentation for the EPIC K-factor equations.
Crossref-only (not read): Maas & Hoffman 1977, Renard & Freimund 1994. Abstract-only: Gravuer et al. 2019. **Not verified / not cited for numbers:** Qadir et al. 2001, Oweis & Hachum 2006, Wei et al. 2016 (only secondary summaries seen).

## 8. Not used
ESA WorldCover / Sentinel-2 (no time), Hassani global maps, AfSIS (see above), JRC GSW (model1's), WDPA.

## 9. Kaggle datasets inspected (public pages, signed-out browser pane; NOT downloaded - download needs login)
| Dataset | What the page shows | Judgement |
|---|---|---|
| ziya07/vegetation-degradation-and-restoration-dataset | 6,000 rows, CC0, columns incl. Restoration_Effect_Class/Score, lat/lon; **no source, no method, no provenance** | cannot be verified as real; likely generated; NOT used |
| colabsss/soil-salinity-sensor-dataset | 27,000 rows, CC0, 38 columns incl. Salinity_Level, Recommended_Action; no coordinates/provenance | NOT used (provenance unknown) |
| agungpambudi/africa-soil-mapping-isdasoil-exploration | 49,225 rows, CC BY 4.0, 10.19 MB = iSDA release of AfSIS (mostly MIR-predicted) | Africa only; not used |
| willianoliveiragibin/different-vegetation-restoration | CC0; 16S OTU table of reclaimed mine soils | not relevant to soil/restoration modelling |
| others seen in search listings (Soil Data Grevena, Agro-Environmental Stress & Failure Simulation (synthetic by its own title), Precision Liming LimeSoDa, JRC erosion datasets) | titles/sizes only | not evaluated further |
