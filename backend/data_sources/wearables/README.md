# Wearables Data Source

Frontend-facing wearable endpoints live in `routes.py` and delegate to
`WearableDataService`.

The current Open Wearables backend implementation is in
`backend/integrations/open_wearables` and uses in-memory local storage for the
MVP. Replace that storage boundary with the WholeYou database when persistence is
added.
