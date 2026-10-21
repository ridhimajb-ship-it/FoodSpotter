# Windows + VS Code setup (no `make` needed)

Prerequisites (install once): **Python 3.12 or 3.13** (python.org – tick "Add python.exe to PATH"), **Node.js 20 or 22 LTS** (nodejs.org), and VS Code with the *Python* and *Pylance* extensions.
Check in a new terminal: `py --version` and `node --version`.

Open the unzipped `foodspotter` folder in VS Code (File → Open Folder), then **Terminal → New Terminal** (PowerShell). Run everything from the project root.

## 1. One-time setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
cd frontend
npm install
cd ..
Copy-Item .env.example .env
```

* If activation fails with "running scripts is disabled": run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use **Command Prompt** and `.venv\Scripts\activate.bat` instead.
* Set an admin token (needed only for the `/api/admin/*` HTTP endpoints; the scripts below don't need it):
  ```powershell
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
  Paste the output after `ADMIN_TOKEN=` in `.env`.
* In VS Code press **Ctrl+Shift+P → Python: Select Interpreter → `.venv`**.

## 2. Load real data (needs internet)

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\discover_restaurants.py                  # all 9 neighbourhoods (~1-2 min, rate-limited on purpose)
# quick trial:  python scripts\discover_restaurants.py --only indiranagar
```

Download the Kaggle dataset (free account): https://www.kaggle.com/datasets/himanshupoddar/zomato-bangalore-restaurants
Save the CSV as `data\zomato.csv`, then:

```powershell
python scripts\import_reviews.py data\zomato.csv        # parse -> match -> dedupe -> NLP -> rank; prints the import report
# optional cap:  python scripts\import_reviews.py data\zomato.csv --max-reviews 5000
```

## 3. Run the app

**Option A – single server (simplest):**
```powershell
cd frontend; npm run build; cd ..
uvicorn backend.main:app --port 8000
```
Open http://localhost:8000 (API docs at http://localhost:8000/docs).

**Option B – development (hot reload), two terminals:**
```powershell
# terminal 1 (project root, venv active)
uvicorn backend.main:app --reload --port 8000
# terminal 2
cd frontend; npm run dev
```
Open http://localhost:5173. (In VS Code you can also start the API with **Run and Debug → "FoodSpotter API (uvicorn)"**.)

### Optional: BERT sentiment (PowerShell, venv active)
```powershell
pip install -r backend\requirements-bert.txt   # transformers + PyTorch, several hundred MB
python scripts\run_bert.py                      # first run downloads the model from Hugging Face
```
Reload the app: the Overview and Methodology pages show which engine is active and BERT's coverage. Without this step the app uses the labelled VADER baseline.

## 4. Tests and evaluation

```powershell
python -m pytest -q                    # backend (142 tests)
cd frontend; npm run typecheck; npm run test; npm run build; cd ..       # frontend (25 tests)
python scripts\evaluate_models.py export-templates   # annotation sheets -> docs\annotation\
python scripts\evaluate_models.py run                # metrics -> docs\evaluation_results.json
```

## 5. Calling admin endpoints from PowerShell (optional)

```powershell
$h = @{ "X-Admin-Token" = "<your ADMIN_TOKEN>" }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/admin/refresh-restaurants -Headers $h -ContentType "application/json" -Body "{}"
Invoke-RestMethod -Uri http://localhost:8000/api/admin/runs -Headers $h
```

## Troubleshooting
* `py` not found → reinstall Python with "Add to PATH", or use `python` instead of `py`.
* Port 8000/5173 busy → add `--port 8001` (and change the proxy target in `frontend\vite.config.ts` for dev mode).
* Admin endpoints return 503 → `ADMIN_TOKEN` is empty in `.env`; restart uvicorn after editing.
* Overpass 429/504 errors → just re-run; results are cached for 24 h per neighbourhood and the client retries with back-off and mirror servers.
* Corporate/VPN networks may block overpass-api.de or kaggle.com; the app still starts and shows empty states with instructions.
