# Economic Pulse

**Cosmo Advisory Co — experimental economic activity dashboard**

An all-free MVP starter based on the Economic Pulse build specification.

## MVP scope
- Synthetic UPI activity series and trend explorer
- Experimental pulse indicator (not official GDP growth)
- Forecast explorer with uncertainty bands and baseline comparison
- Methodology/model-evidence pages
- FastAPI read API
- React + TypeScript + Vite frontend

## Architecture
Frontend: React + TypeScript + Vite · API: FastAPI · Offline training: Python/Colab · Deployment target: Cloudflare Pages + Render · Auth/database target: Supabase.

## Run locally
API:
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
API docs: http://127.0.0.1:8000/docs

Frontend:
```bash
cd frontend
npm install
npm run dev
```
Frontend: http://localhost:5173

Set `VITE_API_BASE_URL=http://127.0.0.1:8000` in `frontend/.env.local` if required.

## Data integrity
Bundled observations and forecasts are **synthetic demonstration data**. They are not official UPI statistics, economic estimates, or investment advice. The pulse score is experimental and must not be described as GDP growth.

## Roadmap
1. Validate the local sample-data MVP.
2. Add provenance-checked public datasets and reproducible offline evaluation.
3. Add Supabase authentication, PostgreSQL persistence and per-user watchlists.
4. Deploy within verified free-plan limits.
5. Add monitoring, backup/restore and security review before accepting private data.

See the 26-page Economic Pulse MVP specification for full design constraints.
