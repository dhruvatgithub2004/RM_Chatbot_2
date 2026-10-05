# RM Co-pilot

Relationship Manager intelligence prototype, built to match `design/RM Copilot.dc.html` (Industry design system).

- **Backend:** FastAPI + SQLAlchemy (SQLite) + pandas, in `backend/`
- **Frontend:** Next.js + React + TypeScript, in `frontend/`
- **Data (synthetic), in `structured_data/`:** `merchant_profiles_v3.csv`, `pos_daily_acquiring_v3.csv`, `merchant_products_held_v2.csv`, `ntb_cross_sell_candidates.csv`; `business_banking_packages_and_charges.md` is reference only

Open decisions and what is not built are in [`BLOCKERS_AND_PENDING_INPUTS.md`](BLOCKERS_AND_PENDING_INPUTS.md).

## Run

```powershell
# 1. Backend (first time)
python -m venv venv
venv\Scripts\python -m pip install -r backend\requirements.txt

cd backend
..\venv\Scripts\python -m app.ingest                       # loads CSVs, computes facts, writes data_quality_report.json
..\venv\Scripts\python -m uvicorn app.main:app --port 8000 # API on :8000

# 2. Frontend (second terminal)
cd frontend
npm install
npm run dev                                                # http://localhost:3000  (proxies /api to :8000)
```

To enable the LLM co-pilots, copy `backend/.env.example` to `backend/.env` and set `LLM_PROVIDER` and the matching key (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`), then restart the backend.

LLM suggestions can be regenerated on their own with `..env\Scripts\python -m app.suggest_llm`. The single knowledge page the LLM reads is `structured_data/rm_product_knowledge.md` (rebuild with `python -m app.knowledge`).

## Tests

```powershell
cd backend
..\venv\Scripts\python -m pytest -q
```

## Screens

| Screen | API |
|---|---|
| Dashboard | `GET /api/dashboard?filter=all\|opp&q=` |
| Profile & analytics | `GET /api/clients?q=`, `GET /api/clients/{id}` |
| Suggestions | `GET /api/suggestions` |
| Co-pilot (portfolio) | `POST /api/copilot/portfolio` |
| Co-pilot (merchant, one client only) | `POST /api/copilot/clients/{id}` |
| Data status | `GET /api/data/status` |
