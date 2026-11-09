# Repository guide

## Purpose

MGeoAI turns saved traffic-news pages into attributed, provenance-preserving accident records, compares model readings
with human annotations, groups articles about the same accident, and shows the result on a map. It fuses evidence; it
does not verify truth or fault. Plain-language method: `METHODOLOGY.md`.

## Layout

- `src/traffic_fusion/extraction/`: preparation, providers, runs, scoring, grouping, incidents, geocode, backup,
  `dataset.py` (public export), `reproduce.py` (rebuild reports from the public dataset), `cli.py` (`mgeoai x ...`).
- `src/traffic_fusion/api/`: FastAPI app, sessions, extraction routes.
- `web/`: React/TypeScript/Vite/Tailwind/MapLibre site. `web/dist` is git-ignored except the assets that are
  force-added for deployment (`git add -f web/dist/index.html web/dist/assets`).
- `assets/mllm_prompts/`: versioned extraction prompt. `docs/`: dataset card and benchmark notes. `journal/`: work log.
- `tests/`: offline tests. `.creds/`, `extraction/`, `annotation/`, `outputs/`, `backups/`: git-ignored, never commit.

## Commands

```bash
python -m pip install -e '.[dev]'
pytest && ruff check src tests && mypy src/traffic_fusion
cd web && npm install && npm test && npm run lint && npm run build
mgeoai serve --extraction-dir extraction --host 127.0.0.1 --port 8000
mgeoai x reproduce --dataset hamimmahmud0/mgeoai-road-accident-news --output reproduced
```

## Engineering rules

- Source pages are untrusted. Scripts and styles are stripped, never executed; article text goes to a model only
  inside a delimited `<ARTICLE_SOURCE>` block that the prompt declares to be data. Model output is schema-validated
  and evidence quotes are checked for verbatim presence. Group ids and annotator answers never reach a model that
  extracts, and annotators never see model output (blind).
- Preserve unknown values (`null`), disagreement and provenance. Never infer fault, sentiment or precise
  coordinates from tragic facts. Place lookups are centres with an uncertainty radius, not crash coordinates.
- A live provider failure stays failed and retryable. Never silently switch provider.
- Tests must be offline. Live calls need explicit credentials, model, timeout and token limits. Cost is optional
  (manually imported prices; `:free` ids cost $0); token limits always apply.
- API keys live in server memory or the environment only. Never log or persist keys, hidden reasoning or passwords.
  Never copy `.creds/` anywhere.
- The public dataset must never contain article text, HTML, images, evidence quotes, raw model replies, real account
  names, annotator notes or timestamps. `dataset.py` refuses to export if it finds them; keep that check.
- Do not delete or overwrite user data without asking. Back up the data root before restarting the live service.
- GeoJSON is WGS84 `[longitude, latitude]`.

## Definition of done

Backend tests, Ruff, mypy, frontend tests/lint/build pass; `mgeoai x reproduce` still matches the published grouping
numbers; provenance survives to the API and reports; secret scans are clean; limitations are documented.
