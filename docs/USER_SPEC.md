# GREEN NOVA AI — Requirements (verbatim from the project owner)

> Binding requirements. Sections kept: sub-agent responsibilities, Model 1, Model 2, ML quality, website,
> technology, domain/deployment, browser/permissions, definition of done.
> Lead-only sections (skill discovery, token management, execution order) are summarized in ORCHESTRATION.md.

Brand name: GREEN NOVA AI — Tagline: Discover. Restore. Grow.

Platform = (1) Agricultural Land Suitability AI model, (2) Agricultural Land Restoration Potential AI model,
(3) premium production-quality website with satellite maps and full integration of both trained models.
Execute the actual work — do not stop at planning or example code.

## Sub-agent responsibilities

### SUB-AGENT 1 — Agricultural Land Suitability Model
Build, train, evaluate and deliver Model 1. Analyze satellite imagery and geospatial environmental data across Jordan,
initially Ma'an Governorate, to identify land suitable for agriculture under current conditions.
Deliverables: dataset acquisition; geospatial preprocessing; model architecture; training pipeline; validation and
testing; model checkpoint; inference pipeline; agricultural suitability maps; land polygon extraction; area
calculations; evaluation report. Works independently on Model 1.

### SUB-AGENT 2 — Agricultural Land Restoration Potential Model
Build, train, evaluate and deliver Model 2. Identify land currently unsuitable for agriculture that could become
suitable through reclamation/restoration. The model must determine: why the land is currently unsuitable; whether the
limitations are reversible; whether restoration is technically feasible; what interventions are appropriate; what
agricultural potential could be achieved after restoration; what constraints and risks remain.
Produce restoration potential maps and detailed land-specific recommendations. Works independently on Model 2.

### SUB-AGENT 3 — Green Nova AI Website
Build the complete website and integrate both models.
PHASE A — FRONTEND FIRST: immediately develop the entire frontend while the ML agents work. Complete: landing page;
branding and design system; dashboard; satellite map interface; Model 1 interface; Model 2 interface; land details
interface; results visualizations; responsive layouts; animations and interactions. Do NOT start backend yet.
Use clearly labeled local demonstration data and frontend state. Do not present mock data as actual AI predictions.
PHASE B — WAIT: after the frontend is completed, wait until both ML agents deliver trained models and working
inference pipelines. Do not block frontend work while waiting.
PHASE C — BACKEND AND INTEGRATION (only after BOTH models are completed): design and implement the production backend;
integrate Model 1 and Model 2; connect frontend API calls to real inference endpoints; connect geospatial outputs to
the satellite map; implement real analysis workflows; test the complete system.
The website agent coordinates with the ML agents through the lead orchestrator.

## 2. MODEL 1 — AGRICULTURAL LAND SUITABILITY INTELLIGENCE

Problem: determine which geographical areas are currently suitable for agricultural cultivation. The system analyzes an
entire selected governorate, not just an uploaded image. Initial target: Jordan, Ma'an Governorate first.

Satellite and geospatial inputs — use: Sentinel-2 multispectral imagery; Sentinel-1 SAR where relevant; NDVI; NDMI;
relevant spectral soil and vegetation indicators; soil pH; soil salinity/EC; soil organic carbon; sand, silt, clay;
soil depth and water-holding capacity; elevation; terrain slope; historical rainfall; temperature; water availability;
environmental and land-use restrictions.

Kaggle datasets — START HERE
- Dataset 1: EuroSAT Sentinel-2 — https://www.kaggle.com/datasets/apollo2506/eurosat-dataset
  Satellite imagery source and for learning multispectral/spatial representations. ~54,600 files, RGB and multispectral
  Sentinel-2. IMPORTANT: EuroSAT labels are land-cover classes, NOT agricultural suitability labels. Do not confuse.
- Dataset 2: Africa Soil Property Prediction Challenge — https://www.kaggle.com/competitions/afsis-soil-properties/data
  Investigate actual files and metadata. Spectral measurements and soil property targets: Calcium, Phosphorus, pH, Soil
  Organic Carbon, Sand. Use where appropriate for soil-property modeling and feature learning.
- Dataset 3: AgriYield 2025 — https://www.kaggle.com/competitions/agriyield-2025/data
  Investigate whether its actual files are accessible and sufficiently documented. Evaluate its field-level soil,
  climate, satellite-index and yield observations as an additional training source. Do not assume labels are verified
  until audited.

Additional research: investigate Kaggle and authoritative geospatial sources for suitable agricultural land labels.
Prioritize FAO GAEZ; Jordan NARC suitability maps; Jordan SOTWIS; SoilGrids; Copernicus Sentinel imagery; digital
elevation data; reliable water and climate datasets. Use Kaggle as the primary discovery/acquisition starting point.
If Kaggle lacks a necessary ground-truth layer, use an authoritative supplementary source and document it.

Required output — classify each geographical land unit into:
1. Currently suitable for agriculture.
2. Suitable with limitations.
3. Requires reclamation.
4. Currently unsuitable.
5. Excluded due to legal or environmental restrictions.
Generate: geospatial suitability raster; individual land polygons; area in dunums and hectares; confidence estimates;
explanations of classification factors; exportable GeoTIFF and GeoJSON outputs.

## 3. MODEL 2 — AGRICULTURAL LAND RESTORATION POTENTIAL

Problem: identify currently unsuitable agricultural land that could be transformed into productive agricultural land
through restoration. Separate model, different objective from Model 1.
Analyze: soil salinity; pH; soil composition; soil organic carbon; soil depth; water availability; rainfall; terrain;
erosion risk; environmental restrictions; restoration constraints.
Determine: 1) what prevents cultivation; 2) can the limitation be reversed; 3) what restoration intervention is
appropriate; 4) estimated restoration feasibility; 5) what suitability could be achieved after restoration; 6) what
water resources and infrastructure would be required; 7) which crop categories could become viable.

Kaggle: start with Africa Soil Property Prediction Challenge (link above). Also investigate additional Kaggle datasets
on: soil degradation; soil salinity; soil erosion; soil organic carbon; soil restoration; agricultural land
degradation; remote sensing of degraded land. Verify the actual files, labels, size, quality and license before
choosing them.
IMPORTANT: Do not invent a Kaggle restoration dataset if none exists. Do not manufacture ground-truth restoration
outcomes. If there is no suitable before-and-after restoration dataset, develop a scientifically justified hybrid
architecture using: ML-based soil property prediction; documented soil constraints; verified restoration studies;
evidence-based intervention scenarios; restoration feasibility estimation. Clearly distinguish REAL OBSERVED data,
EXPERT-DERIVED labels, and SIMULATED outcomes. The output must be a genuine restoration potential assessment, not a
generic recommendation chatbot.

## 4. MACHINE LEARNING QUALITY REQUIREMENTS

Both models must generalize to unseen geographical regions. Overfitting prevention is critical. Implement:
geographic train/validation/test splits; spatial cross-validation where feasible; temporal validation where
applicable; duplicate and near-duplicate detection; leakage prevention; class balancing; appropriate augmentation;
regularization; early stopping; hyperparameter tuning; model calibration; uncertainty estimation.
Never use random pixel splitting as the only validation strategy.
Model 1 evaluate: accuracy; macro F1; precision; recall; confusion matrix; IoU where segmentation applies; calibration.
Model 2 evaluate: MAE; RMSE; R² where meaningful; feasibility classification precision and recall; calibration and
uncertainty; performance on geographically held-out areas.
Never fabricate accuracy or claim a model has no overfitting. Do not force 99% accuracy. Prioritize trustworthy
performance on unseen geographical regions. Preserve the native resolution of every dataset and never claim more
spatial precision than the source supports.

## 5. GREEN NOVA AI WEBSITE

Must look like a premium international geospatial intelligence platform.
Design: deep forest green; sophisticated charcoal; warm off-white; restrained natural green accents; high-quality
satellite imagery; premium typography; excellent spacing; elegant transitions; responsive design.
Avoid generic AI dashboard templates, excessive gradients, excessive glass effects, generic AI illustrations. It should
look like a serious professional technology product.

A. Landing Page: branding; premium hero; satellite imagery; project introduction; agricultural land discovery;
   agricultural restoration intelligence; how it works; product capabilities; entry to the intelligence dashboard.
B. Intelligence Dashboard: interactive satellite map; country selector; governorate selector; Jordan initial country;
   Ma'an initial demonstration region; land suitability layers; restoration potential layers; land area statistics;
   analysis status; filters and map legends.
C. Land Suitability (Model 1): select a region; start an analysis; view satellite imagery; view suitability overlays;
   click individual land polygons; inspect suitability details; area in dunums and hectares; review model
   confidence; export analysis results.
D. Land Restoration (Model 2): select currently unsuitable land; run restoration potential analysis; review the
   constraints; compare restoration scenarios; view intervention recommendations; inspect estimated water
   requirements; review potential agricultural use; compare current and simulated post-restoration suitability;
   export detailed reports.
E. Land Details: coordinates; land area; current suitability; soil characteristics; terrain; water indicators;
   restoration potential; model confidence; limitations; recommendations.

## 6. WEBSITE TECHNOLOGY

Modern, maintainable stack. Preferred: React/Next.js with TypeScript; Tailwind CSS; MapLibre GL JS (or similar);
FastAPI backend; Python model-serving layer; GeoJSON and GeoTIFF support. Choose alternatives only when technically
justified. The frontend agent finishes the frontend first; only after both models are ready implements backend and real
integration. Do not create fake inference endpoints or present demonstration results as real model predictions.

## 7. DOMAIN AND DEPLOYMENT

The owner already owns a domain for Green Nova AI. Use the existing domain if discoverable in project configuration or
existing deployment settings. Do not buy a new domain. Do not invent the domain name. Do not ask unnecessary
questions. If the exact domain is not available, prepare a configurable env var such as GREEN_NOVA_DOMAIN and continue.
Prepare: production build; HTTPS configuration; frontend and backend deployment configuration; environment variables;
secure secrets management; API configuration; DNS instructions if required. Do not claim the website is live until
deployment is actually verified.

## 9. BROWSER, TOOLS AND PERMISSIONS

Use the existing browser session/profile for: Kaggle dataset research; dataset verification; public documentation;
geospatial source research; downloading accessible datasets; technical references. Use terminal, filesystem, Python,
GPU and browser tools. Use Kaggle API credentials if already configured; if unavailable, use the existing browser
session or other legitimate public download methods. Proceed autonomously for routine development steps (read/write
project files, create folders/scripts, install dependencies, download public datasets, run training/tests, build
frontend/backend, generate docs, prepare deployment files). Do not expose credentials, tokens or API keys. Do not bypass
platform security restrictions. If an external irreversible action requires unavailable authorization (purchasing a
service, changing DNS, publishing to production) prepare everything possible and document the remaining blocker.

## 12. DEFINITION OF DONE

MODEL 1: dataset acquired and verified; training completed; independent evaluation completed; checkpoint saved;
inference works; geospatial suitability maps generated.
MODEL 2: dataset sources verified; restoration methodology implemented; training or defensible hybrid modeling
completed; evaluation completed; checkpoint saved where applicable; inference works; restoration potential maps
generated.
WEBSITE: premium frontend completed; backend implemented after model completion; both real models integrated;
satellite map functional; land polygons selectable; real analysis results displayed; reports and exports working.
FINAL REPORT must cover: exact model architectures; exact Kaggle dataset links; dataset sizes and licenses; training
configurations; evaluation metrics; geographic validation methodology; checkpoint locations; website architecture; API
documentation; known limitations; deployment instructions.
