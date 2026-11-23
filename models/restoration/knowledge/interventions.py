"""Intervention library.  Every effect is `simulated`/`expert_rule`: ranges come from the documents in sources.py or are flagged `assumed`.

`expected_effect` text is generated per unit from the engine's numbers (see assemble.py); this module holds the static description, the factor targeted
and the honest source references.
"""
from __future__ import annotations

from .sources import ref

INTERVENTIONS = {
    "drip_irrigation": dict(
        name="Pressurised drip irrigation with fertigation",
        description="Replaces rainfall deficit with metered water at ~80-92 % application efficiency (assumed range), allows leaching fraction control and fertigation on sandy/low-SOC soils.",
        targets_factor="water_availability", evidence="expert_rule", source_refs=ref("FAO56", "FAO_IDP29")),
    "leaching_reclamation": dict(
        name="Reclamation leaching and sustained leaching fraction",
        description="Apply water in excess of crop ET so that salts move below the root zone: initial reclamation depth r (m water per m soil, C/C0 = exp(-k r)) then a maintenance "
                    "leaching fraction LR = ECw/(5 ECe - ECw). Needs drainage and a leachate disposal route.",
        targets_factor="salinity", evidence="expert_rule", source_refs=ref("FAO_IDP29")),
    "gypsum_amendment": dict(
        name="Gypsum (or other soluble-Ca) amendment with leaching",
        description="Replaces exchangeable Na by Ca (0.86 g gypsum per kg soil per cmol(c)/kg of Na replaced, i.e. 1.92 t/ha pure gypsum per cmol(c)/kg for 0.15 m at 1.49 g/cm3), "
                    "then leach the displaced Na.  Effectiveness fraction 0.5-0.9 assumed.",
        targets_factor="sodicity", evidence="expert_rule", source_refs=ref("FAO_SB39", "FAO_IDP29")),
    "organic_amendment": dict(
        name="Organic amendment / mulch (compost, manure, crop residue)",
        description="Raises topsoil SOC, structure and water holding; qualitative support from a rangeland meta-analysis (arid/semiarid/Mediterranean): soil carbon and water-holding capacity increase, runoff decreases; "
                    "quantitative gain in this model (+0.05-0.40 % SOC over ~5 yr) is an ASSUMED range.  Low-N amendments preferred.",
        targets_factor="organic_carbon", evidence="expert_rule", source_refs=ref("GRAVUER_2019")),
    "terracing": dict(
        name="Bench terraces with stone/earth risers and runoff diversion",
        description="Converts slopes up to a practical limit (assumed 20-30 deg, soil depth >= 40 cm) into cultivable benches and reduces water erosion; abandonment/poor maintenance is the main failure mode.",
        targets_factor="slope_erosion", evidence="expert_rule", source_refs=[]),
    "water_harvesting": dict(
        name="Microcatchment / contour-bund water harvesting",
        description="Concentrates runoff onto the cultivated area: catchment:cultivated ratio C:CA = (WR - DR)/(DR K EFF), K 0.1-0.5, EFF 0.5-0.75, design rainfall DR at 67 % exceedance. "
                    "Rainfall in this region is highly variable (FAO: 100 mm/yr -> 30-350 % of mean), so failure years are expected.",
        targets_factor="water_availability", evidence="expert_rule", source_refs=ref("FAO_WH91")),
    "salt_tolerant_crops": dict(
        name="Salt/sodicity-tolerant crop selection (date palm, barley, tall wheatgrass, olive)",
        description="Choose crops whose Maas-Hoffman threshold exceeds the achievable root-zone ECe (FAO Table 4) and whose ESP class tolerates the residual sodicity.",
        targets_factor="salinity", evidence="expert_rule", source_refs=ref("FAO_IDP29", "FAO_SB39")),
    "drainage": dict(
        name="Subsurface/open drainage and leachate disposal (evaporation pond)",
        description="Leaching only works if leachate can leave the root zone; saline basins with shallow saline water tables are effectively non-reclaimable. No water-table data are available "
                    "here, so drainage feasibility is probabilistic (decreasing with initial ECe).",
        targets_factor="salinity", evidence="expert_rule", source_refs=ref("FAO_IDP29")),
}

FACTOR_REVERSIBILITY_RULES = """
salinity   : reversible if ECe <= 16 dS/m and not a salt flat; partially_reversible 16-30; irreversible if ECe >= 30 or salt flat (assumed thresholds; FAO_IDP29: leaching needs drainage)
sodicity   : reversible if gypsum need <= 15 t/ha, partially_reversible up to ESP 50, irreversible above (assumed)
alkalinity : partially_reversible (calcareous buffering; pH cannot be permanently lowered at scale)
organic_carbon: reversible (slow; limited by climate)
texture    : partially_reversible (organic amendment only; sand/clay content itself not changeable)
coarse_fragments: partially_reversible (stone removal is costly)
soil_depth : irreversible below 30 cm, partially_reversible 30-60 cm (soil cannot be created at scale)
slope      : reversible <= 10 deg (contouring), partially_reversible by terracing up to the terrace limit, irreversible above 30 deg
erosion    : reversible (conservation measures)
water_availability: partially_reversible (climate aridity itself cannot be changed; compensated by imported/harvested water)
restriction: irreversible (Model 1 class 5 legal/environmental restriction)
"""
