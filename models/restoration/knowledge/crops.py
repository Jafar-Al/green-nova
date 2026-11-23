"""Crop parameter table (expert_rule evidence; every number's origin is stated in `src`).

Salinity: FAO_IDP29 Table 4 ECe at 100/90/75/50/0 % yield potential (read in the source HTML).  Maas-Hoffman line:
Y = 100 - b (ECe - a), a = ECe at 100 %, b = 100/(ECe_0 - a)  (FAO_IDP29 eq. 10).
Crop coefficients: FAO56 Table 12 (Kc ini / mid / end); stage lengths FAO56 Table 11 (read rows noted per crop); rooting depth FAO56 Table 22.
Sodicity tolerance: FAO_SB39 Table 32 (Abrol 1982): serious yield loss above ESP ~55 (tolerant) / ~35 (semi-tolerant) / ~10 (sensitive);
Pearson (1960) Table 33 lists deciduous fruit, nuts, citrus, avocado as extremely sensitive (ESP 2-10).
Anything NOT in those documents is flagged `assumed` in `notes` (olive/almond salinity & stage lengths, date-palm ESP class ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

# ---- FAO_IDP29 Table 4 (ECe, dS/m) for the crops used + the 'moderately tolerant' (Table 5) members used for a class-median proxy
# order: ECe at 100 %, 90 %, 75 %, 50 %, 0 % yield potential
T4 = {
    "barley": (8.0, 10, 13, 18, 28), "cotton": (7.7, 9.6, 13, 17, 27), "wheat": (6.0, 7.4, 9.5, 13, 20),
    "wheat_durum": (5.7, 7.6, 10, 15, 24), "sorghum": (6.8, 7.4, 8.4, 9.9, 13), "soybean": (5.0, 5.5, 6.3, 7.5, 10),
    "cowpea": (4.9, 5.7, 7.0, 9.1, 13), "squash_zucchini": (4.7, 5.8, 7.4, 10, 15), "beet_red": (4.0, 5.1, 6.8, 9.6, 15),
    "tomato": (2.5, 3.5, 5.0, 7.6, 13), "tall_wheatgrass": (7.5, 9.9, 13, 19, 31), "bermuda_grass": (6.9, 8.5, 11, 15, 23),
    "barley_forage": (6.0, 7.4, 9.5, 13, 20), "ryegrass_perennial": (5.6, 6.9, 8.9, 12, 19),
    "trefoil_narrowleaf": (5.0, 6.0, 7.5, 10, 15), "harding_grass": (4.6, 5.9, 7.9, 11, 18), "tall_fescue": (3.9, 5.5, 7.8, 12, 20),
    "wheatgrass_std_crested": (3.5, 6.0, 9.8, 16, 28), "sudan_grass": (2.8, 5.1, 8.6, 14, 26), "wildrye_beardless": (2.7, 4.4, 6.9, 11, 19),
    "alfalfa": (2.0, 3.4, 5.4, 8.8, 16), "date_palm": (4.0, 6.8, 11, 18, 32), "orange": (1.7, 2.3, 3.3, 4.8, 8.0),
    "grape": (1.5, 2.5, 4.1, 6.7, 12), "almond": (1.5, 2.0, 2.8, 4.1, 6.8),
}
# Table 5 'moderately tolerant' members that also have Table 4 rows (used to build the olive proxy)
T5_MODERATELY_TOLERANT_WITH_T4 = ["wheat", "wheat_durum", "sorghum", "soybean", "cowpea", "squash_zucchini", "beet_red", "barley_forage",
                                  "ryegrass_perennial", "trefoil_narrowleaf", "harding_grass", "tall_fescue", "wheatgrass_std_crested",
                                  "sudan_grass", "wildrye_beardless"]


def mt_class_proxy():
    a = median(T4[k][0] for k in T5_MODERATELY_TOLERANT_WITH_T4)
    e0 = median(T4[k][4] for k in T5_MODERATELY_TOLERANT_WITH_T4)
    return (a, None, None, None, e0)


ESP_ONSET = {"tolerant": 55.0, "semi_tolerant": 35.0, "sensitive": 10.0, "extremely_sensitive": 6.0}
# FAO_SB39 Table 32/33: ESP above which yields are seriously affected. 'extremely_sensitive' = lower end of Pearson's 2-10 band, assumed 6
# (Hassani et al. also use ESP >= 6 as their sodicity indicator).


@dataclass
class Crop:
    id: str
    name: str
    category: str                     # crop_categories vocabulary
    ece: tuple                        # (a, e90, e75, e50, e0)
    esp_class: str
    kc: tuple                         # (ini, mid, end)
    plant_doy: int
    stages: tuple                     # (Lini, Ldev, Lmid, Llate) days; ignored for evergreen
    zr_m: tuple                       # FAO56 Table 22 max effective root depth range (m)
    evergreen_kc: float | None = None  # constant Kc for evergreen/perennial-year-round crops
    perennial: bool = False
    frost_sensitive: bool = False
    rainfed_ok: bool = False          # crops commonly grown rainfed/with harvested water in arid/semi-arid WANA (used only to pick WH scenario crops)
    notes: str = ""
    src: dict = field(default_factory=dict)

    @property
    def a(self):
        return self.ece[0]

    @property
    def b(self):                      # % yield loss per dS/m
        return 100.0 / (self.ece[4] - self.ece[0])


def _crop(**kw):
    return Crop(**kw)


_olive_ece = mt_class_proxy()

CROPS = {c.id: c for c in [
    _crop(id="barley", name="Barley (grain)", category="cereals", ece=T4["barley"], esp_class="semi_tolerant", kc=(0.30, 1.15, 0.25),
          plant_doy=335, stages=(20, 60, 70, 30), zr_m=(1.0, 1.5), rainfed_ok=True,
          notes="Stage lengths: FAO56 Table 11 'Winter wheat, Calif. desert, Dec planting' (20/60/70/30 = 180 d) used as analogue for Ma'an winter cereals.",
          src=dict(ece="FAO_IDP29 T4", kc="FAO56 T12 (cereals ini 0.3; barley mid 1.15, end 0.25)", zr="FAO56 T22", esp="FAO_SB39 T32 (semi-tolerant)")),
    _crop(id="wheat", name="Wheat", category="cereals", ece=T4["wheat"], esp_class="semi_tolerant", kc=(0.30, 1.15, 0.30),
          plant_doy=335, stages=(20, 60, 70, 30), zr_m=(1.0, 1.5), rainfed_ok=True,
          notes="Kc end 0.25-0.40 in Table 12 (midpoint 0.30 used). Stage lengths as for barley.",
          src=dict(ece="FAO_IDP29 T4", kc="FAO56 T12", zr="FAO56 T22 (spring wheat; winter wheat 1.5-1.8)", esp="FAO_SB39 T32")),
    _crop(id="alfalfa", name="Alfalfa (hay)", category="forage", ece=T4["alfalfa"], esp_class="semi_tolerant", kc=(0.40, 0.95, 0.90),
          plant_doy=60, stages=(10, 30, 180, 40), zr_m=(1.0, 2.0), perennial=True,
          notes="Kc 'averaged cutting effects' (FAO56 T12). Season Mar-Oct is an assumption (winter dormancy at ~1000 m); stage lengths assumed. ESP class assumed semi-tolerant (Pearson 1960 lists alfalfa as tolerant).",
          src=dict(ece="FAO_IDP29 T4", kc="FAO56 T12 (alfalfa hay, averaged cutting effects)", zr="FAO56 T22")),
    _crop(id="sudan_grass", name="Sudan grass (forage)", category="forage", ece=T4["sudan_grass"], esp_class="semi_tolerant", kc=(0.50, 0.90, 0.85),
          plant_doy=120, stages=(15, 25, 60, 30), zr_m=(1.0, 1.5),
          notes="Kc 'averaged cutting effects' FAO56 T12; summer annual, 130-day season assumed.",
          src=dict(ece="FAO_IDP29 T4", kc="FAO56 T12", zr="FAO56 T22")),
    _crop(id="tall_wheatgrass", name="Tall wheatgrass (salt-tolerant forage proxy)", category="forage", ece=T4["tall_wheatgrass"], esp_class="tolerant",
          kc=(0.40, 0.95, 0.85), plant_doy=60, stages=(10, 30, 180, 40), zr_m=(0.5, 1.5), perennial=True,
          notes="Stands in for the salt-tolerant forage group (Table 5 'tolerant' grasses/halophytes). Kc: FAO56 T12 'Grazing pasture, rotated grazing' (0.40 / 0.85-1.05 / 0.85, mid 0.95 used).",
          src=dict(ece="FAO_IDP29 T4", kc="FAO56 T12 (grazing pasture)", esp="FAO_SB39 T33 (most tolerant: crested/tall wheatgrass)")),
    _crop(id="date_palm", name="Date palm", category="salt_tolerant_perennial", ece=T4["date_palm"], esp_class="semi_tolerant", kc=(0.90, 0.95, 0.95),
          plant_doy=1, stages=(0, 0, 0, 0), zr_m=(1.5, 2.5), evergreen_kc=0.95, perennial=True, frost_sensitive=True,
          notes="Kc 0.90/0.95/0.95 (FAO56 T12). ESP class assumed (date palm not listed in FAO_SB39). Cold-winter plateau => frost/chill risk flagged separately.",
          src=dict(ece="FAO_IDP29 T4", kc="FAO56 T12 (date palms)", zr="FAO56 T22")),
    _crop(id="olive", name="Olive", category="tree_and_vine", ece=_olive_ece, esp_class="sensitive", kc=(0.65, 0.70, 0.70),
          plant_doy=60, stages=(30, 90, 60, 90), zr_m=(1.2, 1.7), perennial=True, rainfed_ok=True,
          notes="FAO_IDP29 Table 5 rates olive 'moderately tolerant' but gives no Table 4 row: salinity parameters here are the MEDIAN of the Table 4 rows of all Table 5 "
                "'moderately tolerant' crops (class proxy, assumed). ESP class assumed sensitive. Stage lengths FAO56 T11 olives 30/90/60/90 (March, Mediterranean).",
          src=dict(ece="proxy from FAO_IDP29 T4 x T5 (assumed)", kc="FAO56 T12 (olives, 40-60 % canopy)", zr="FAO56 T22")),
    _crop(id="almond", name="Almond", category="tree_and_vine", ece=T4["almond"], esp_class="extremely_sensitive", kc=(0.40, 0.90, 0.65),
          plant_doy=60, stages=(20, 60, 30, 40), zr_m=(1.0, 2.0), perennial=True, frost_sensitive=True, rainfed_ok=False,
          notes="FAO56 Table 11 has no almond row: pistachio stage lengths (20/60/30/40) used as analogue (assumed). Table 4 tree-growth based tolerance. ESP: Pearson (nuts) extremely sensitive.",
          src=dict(ece="FAO_IDP29 T4 (tolerance based on tree growth)", kc="FAO56 T12 (almonds, no ground cover)", zr="FAO56 T22", esp="FAO_SB39 T33")),
    _crop(id="grape", name="Table grape", category="tree_and_vine", ece=T4["grape"], esp_class="sensitive", kc=(0.30, 0.85, 0.45),
          plant_doy=91, stages=(20, 40, 120, 60), zr_m=(1.0, 2.0), perennial=True, frost_sensitive=True,
          notes="Stage lengths FAO56 T11 grapes 20/40/120/60 (April, low latitudes). ESP class assumed sensitive.",
          src=dict(ece="FAO_IDP29 T4 (tree growth)", kc="FAO56 T12 (grapes, table or raisin)", zr="FAO56 T22")),
    _crop(id="orange", name="Orange (citrus)", category="tree_and_vine", ece=T4["orange"], esp_class="extremely_sensitive", kc=(0.70, 0.65, 0.70),
          plant_doy=60, stages=(60, 90, 120, 30), zr_m=(1.2, 1.5), perennial=True, frost_sensitive=True,
          notes="Stage lengths FAO56 T11 citrus 60/90/120/30 (March, Calif.). Kc FAO56 T12 'Citrus, no ground cover, 70 % canopy'.",
          src=dict(ece="FAO_IDP29 T4", kc="FAO56 T12", zr="FAO56 T22", esp="FAO_SB39 T33 (citrus extremely sensitive)")),
    _crop(id="tomato", name="Tomato", category="vegetables", ece=T4["tomato"], esp_class="semi_tolerant", kc=(0.60, 1.15, 0.80),
          plant_doy=75, stages=(35, 40, 50, 30), zr_m=(0.7, 1.5),
          notes="FAO56 T11 'Arid region, January planting' stage lengths 35/40/50/30 (155 d) shifted to mid-March for the cold plateau (assumed). Kc end 0.70-0.90 (0.80 used). ESP class assumed semi-tolerant (Pearson lists tomato as tolerant).",
          src=dict(ece="FAO_IDP29 T4", kc="FAO56 T12 (tomato)", zr="FAO56 T22")),
]}

CATEGORY_LABELS = {
    "cereals": "Cereals (barley, wheat)",
    "forage": "Forage (alfalfa, Sudan grass, salt-tolerant grasses)",
    "salt_tolerant_perennial": "Date palm / salt-tolerant perennials",
    "tree_and_vine": "Tree and vine crops (olive, almond, grape, citrus)",
    "vegetables": "Vegetables (tomato)",
}


def rel_yield_salinity(crop: Crop, ece):
    """Maas-Hoffman relative yield in [0,1] (FAO_IDP29 eq. 10), works on numpy arrays."""
    import numpy as np
    return np.clip(1.0 - crop.b / 100.0 * np.maximum(ece - crop.a, 0.0), 0.0, 1.0)


def esp_onset(crop: Crop) -> float:
    return ESP_ONSET[crop.esp_class]
