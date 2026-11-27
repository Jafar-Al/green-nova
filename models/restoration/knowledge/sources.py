"""Registry of the studies/documents the restoration engine draws on.

Rule: an entry is only listed with `verified` text that says exactly what was checked and how. Nothing is cited from memory.
`level`:  full_text   = the cited numbers/equations were read in the publisher's/FAO's document by the authors
          abstract    = only the abstract/bibliographic record was read (qualitative statements only are used)
          crossref    = bibliographic record resolved in Crossref (existence + authors + venue + year), content not read
          pending     = not yet verified (not used for any number)
"""
from __future__ import annotations

SOURCES = {
    "FAO_IDP29": dict(
        citation="Ayers, R.S. & Westcot, D.W. (1985). Water quality for agriculture. FAO Irrigation and Drainage Paper 29 Rev. 1.",
        url="https://www.fao.org/4/t0234e/t0234e00.htm", level="full_text",
        verified="Read ch.2-3 (HTML): Table 4 crop ECe/ECw yield-potential values (100/90/75/50/0 %), Y = 100 - b(ECe - a) (eq. 10), "
                 "leaching requirement worked example (ECw 1.2, ECe 2.5 -> LR 0.10; ECe 1.7 -> 0.16), ECe = 1.5 ECw at LF 0.15-0.20, "
                 "reclamation leaching: 70-80 % (continuous ponding) / 80-90 % (intermittent/sprinkler) salt removal per depth of water "
                 "equal to soil depth; ECe < 10-12 dS/m needs only 10-20 cm pre-plant irrigation for barley/cotton; gypsum equivalent 86 kg per me/L per 1000 m3."),
    "FAO56": dict(
        citation="Allen, R.G., Pereira, L.S., Raes, D. & Smith, M. (1998). Crop evapotranspiration - Guidelines for computing crop water requirements. FAO Irrigation and Drainage Paper 56.",
        url="https://www.fao.org/4/x0490e/x0490e00.htm", level="full_text",
        verified="Read ch.3 (Hargreaves eq. 52: ETo = 0.0023 (Tmean+17.8)(Tmax-Tmin)^0.5 Ra), ch.6 Table 11 (stage lengths) and Table 12 (Kc ini/mid/end) rows used in crops.py."),
    "FAO_SB55": dict(
        citation="FAO (1985). Guidelines: Land evaluation for irrigated agriculture. FAO Soils Bulletin 55.",
        url="https://www.fao.org/3/x5648e/x5648e00.htm", level="full_text",
        verified="Read ch.2 and ch.4: land suitability classes S1/S2/S3/N1/N2, relative yield as land productivity index ('top of S2 taken as 80 %, "
                 "S3 as 60 %'); class-determining factors incl. effective soil depth, stoniness, ESP/salinity, slope, drainage, water supply. "
                 "The 40 % lower bound of S3 used here is NOT stated in the text (assumption, sensitivity-tested)."),
    "FAO_SB39": dict(
        citation="Abrol, I.P., Yadav, J.S.P. & Massoud, F.I. (1988). Salt-affected soils and their management. FAO Soils Bulletin 39.",
        url="https://www.fao.org/4/x5871e/x5871e00.htm", level="full_text",
        verified="Read ch.4: ESP 15 = sodic limit (Richards 1954), saturation-paste pH 8.2 diagnostic, Table 32 (Abrol 1982) crop ESP tolerance classes "
                 "(yields seriously affected above ESP ~55 tolerant / ~35 semi-tolerant / ~10 sensitive), Table 33 (Pearson 1960), Table 23 hazard classes, "
                 "gypsum stoichiometry worked example (0.5 cmol Ca/kg, 15 cm -> 1.96 t/ha pure gypsum)."),
    "FAO_WH91": dict(
        citation="Critchley, W. & Siegert, K. (1991). A manual for the design and construction of water harvesting schemes for plant production. FAO AGL/MISC/17/91.",
        url="https://www.fao.org/3/u3160e/u3160e00.htm", level="full_text",
        verified="Read ch.3-4: WATER HARVESTED = CA x design rainfall x runoff coeff. x efficiency; C:CA = (WR - DR)/(DR x K x EFF); K usually 0.1-0.5; EFF 0.5-0.75; "
                 "design rainfall at 67-75 % exceedance; rainfall variability (mean 200-300 mm: 40-200 % of mean in 19/20 yr; 100 mm: 30-350 %); microcatchment C:CA 2-3:1 guideline."),
    "MAAS_HOFFMAN_1977": dict(
        citation="Maas, E.V. & Hoffman, G.J. (1977). Crop salt tolerance - current assessment. J. Irrigation and Drainage Div. ASCE 103(IR2):115-134.",
        url="https://doi.org/10.1061/jrcea4.0001137", level="crossref",
        verified="Crossref record resolved (title, authors Maas/Hoffman, journal, 1977). Numerical thresholds are taken from the FAO_IDP29 Table 4 adaptation, not from the paper."),
    "RENARD_FREIMUND_1994": dict(
        citation="Renard, K.G. & Freimund, J.R. (1994). Using monthly precipitation data to estimate the R-factor in the revised USLE. J. Hydrology 157:287-306.",
        url="https://doi.org/10.1016/0022-1694(94)90110-4", level="crossref",
        verified="Crossref record resolved. The R-factor regression coefficients used in erosion.py are NOT taken from this paper unless stated in erosion.py (see there)."),
    "SWATPLUS_K": dict(
        citation="SWAT+ Input/Output documentation, 'Soil Erodibility Factor' (equations of Williams, J.R. 1995, EPIC).",
        url="https://swatplus.gitbook.io/io-docs/sediment/musle/soil-erodibility-factor", level="full_text",
        verified="Read the four EPIC factor equations f_csand, f_cl-si, f_orgc, f_hisand (as transcribed in erosion.py). Williams (1995) itself was not read."),
    "GRAVUER_2019": dict(
        citation="Gravuer, K., Gennet, S. & Throop, H.L. (2019). Organic amendment additions to rangelands: a meta-analysis of multiple ecosystem outcomes. Global Change Biology 25:1152-1170.",
        url="https://doi.org/10.1111/gcb.14535", level="abstract",
        verified="Abstract read via Europe PMC (PMC6849820): 92 studies in arid/semiarid/Mediterranean rangelands; amendments on average increased soil carbon, water-holding capacity, ANPP; "
                 "decreased runoff; short study durations (median 1-2 yr). No numeric effect size was read -> used only qualitatively."),
    "HASSANI_2020": dict(
        citation="Hassani, A., Azapagic, A. & Shokri, N. (2020). Predicting long-term dynamics of soil salinity and sodicity on a global scale. PNAS 117(52):33017-33027.",
        url="https://data.mendeley.com/datasets/v9mgbmtnf2/1", level="abstract",
        verified="Dataset record read (Mendeley Data, CC BY 4.0, DOI 10.17632/v9mgbmtnf2.1): global ECe/ESP 0-30 cm maps 1980-2018, ~1 km, ML-based; file list/sizes read via public API. Paper not read in full."),
    "BATJES_2024": dict(
        citation="Batjes, N.H., Calisto, L. & de Sousa, L.M. (2024). Providing quality-assessed and standardised soil data to support global mapping and modelling (WoSIS snapshot 2023). Earth Syst. Sci. Data 16:4735-4765.",
        url="https://doi.org/10.5194/essd-16-4735-2024", level="abstract",
        verified="Article landing page read: ~228k profiles, EC (ELCOSP = saturated paste) among standardised properties, per-record licences (CC BY / CC BY-NC / public domain), "
                 "positional uncertainty ~100 m for 86 % of profiles, purposive (non-probabilistic) sampling."),
    "POGGIO_2021": dict(
        citation="Poggio, L. et al. (2021). SoilGrids 2.0: producing soil information for the globe with quantified spatial uncertainty. SOIL 7:217-240.",
        url="https://doi.org/10.5194/soil-7-217-2021", level="pending",
        verified="Not yet read; SoilGrids 2.0 is used as a third-party ML prior with its own quantiles (files.isric.org, CC BY 4.0)."),
}


def ref(*ids: str):
    """Return source_refs strings (id + url) for the contract's `source_refs` field."""
    out = []
    for i in ids:
        s = SOURCES[i]
        out.append(f"{i}: {s['citation']} <{s['url']}> [verified: {s['level']}]")
    return out
