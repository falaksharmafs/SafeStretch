# Model card - Road risk scoring

**Purpose:** prioritise road segments for safety audits and give drivers a relative risk signal. Not for assigning blame, insurance pricing, or enforcement targeting of individuals.

**Data:** reported police/open accident records (location, time, severity), OpenStreetMap network and POIs, Open-Meteo weather. No driver or vehicle identifiers are stored. Crowdsourced reports store only a salted hash of the IP, and stay `pending` until moderated.

**Models:** (1) LightGBM segment x quarter classifier with isotonic calibration; (2) Empirical-Bayes expected-crash ranking with an exposure proxy; (3) learned hour-of-day and rain multipliers; (4) DBSCAN hotspots.

**Validation:** spatial block cross-validation, temporal hold-out, history-only baseline, calibration table and Brier score. Report these numbers - not accuracy.

**Known limitations**
* Under-reporting, especially minor and two-wheeler crashes, and in rural areas.
* Exposure is a proxy unless traffic counts are supplied; busy roads can still be over-ranked.
* Hour multipliers include traffic volume by design; the live score is a relative index.
* OSM attributes (speed, lanes) are incomplete in many Indian cities.
* Associations only: SHAP reasons and intervention estimates are not causal proof.
* Coordinates are often approximate; snapping uses a 50 m cap.

**Bias check to run:** compare recall in the top 5% across areas (centre vs periphery, road classes). If peripheral areas are systematically missed, state it.

**Safe use:** show the disclaimer, never present scores as certain, review high-ranked segments with an engineer before acting.
