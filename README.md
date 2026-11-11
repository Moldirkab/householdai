# HouseholdAI: shared household budget with AI forecasts

Prototype for the research project *Personal Finance Manager with AI: Collaborative Household Budgeting System* (Objective 1).
Several people share one household budget: they track expenses, agree on a monthly plan per category, and get a
**next-month forecast from the best model per category (SARIMA, ARIMA or MA(3))** with **AI recommendations**
(LLM, with a rule-based fallback).

## Run it (Windows, macOS, Linux)

Requirements: **Python 3.10 or newer** (python.org). Node.js is **not** needed: the interface is already built (`frontend/dist`).

- **Windows:** double-click `start.bat`
- **macOS / Linux:** in a terminal, `./start.sh`

The first start creates a virtual environment and installs packages (a few minutes). Then open **http://localhost:8000**.
Stop with `Ctrl+C`. Data is saved in `backend/householdai.db`.

Other devices on the same Wi-Fi (e.g. survey participants' phones) can open `http://<your-laptop-IP>:8000`
(find the IP with `ipconfig` on Windows or `ifconfig` on macOS; allow Python through the firewall if asked).

## Data: what is real and where it comes from

The app contains **no invented data**.

| Data | Source | Where it is used |
|---|---|---|
| **Research dataset** `backend/data/ce_monthly_2017_2024.csv` | Real BLS Consumer Expenditure Survey microdata, processed in the research notebook `CE_SARIMA_2017_2024.ipynb`: weighted average monthly expenditure per U.S. household by category, Jan 2017 – Dec 2024 (USD) | Demo household data; seasonal pattern for households with short history |
| **Demo household G1** | Exactly the research dataset: one read-only record per real monthly category value, with the real dates (Food is stored as its real parts, Groceries and Dining out) | App demonstration and the survey |
| **Your own households** | Expenses that you and your members enter | Your forecasts |

The demo household is labelled on every page as BLS data. It is **not** the personal spending of anyone in it, it has no
fictional members, and its records cannot be edited. No budgets are pre-set: plans are suggested from the last three
months (and marked "suggested") until members save their own.

## Demo household and survey groups

Created automatically on first start: **Demo household G1 (BLS data)**.

- Demo login: **`g1.demo@demo.kz`**, password **`demo1234`** (owner).
- Participants **create their own account** and choose *Join with an invite code*: **`DEMOG1`**.

One household per survey group of 2–3 students: stop the app, then in `backend` (with the virtual environment active):

```
python -m app.seed --groups 6          # creates G1 ... G6 (codes DEMOG1 ... DEMOG6, logins g2.demo@demo.kz, ...)
python -m app.seed --reset --groups 6  # deletes everything and starts again
```
Activate the environment first: `backend\.venv\Scripts\activate` (Windows) or `source backend/.venv/bin/activate` (macOS/Linux).
**If you used an earlier version of the app, run `python -m app.seed --reset` once** to remove the old demo data.

In the demo household the latest data month is December 2024, so the Forecast page opens on **January 2025**
(one month after the data). Use ← to go back to any month of 2024 and press *Show actual spending* to compare the
forecast with the real BLS value, as in the research test year.

## AI recommendations (LLM)

Copy `backend/.env.example` to `backend/.env` and set `LLM_PROVIDER` (`anthropic`, `openai` or `gemini`) and `LLM_API_KEY`.
Restart the app. Without a key, or if the LLM call fails, the app shows **rule-based** recommendations (the same rules as the
questionnaire demo) and says so on the page. Only forecast numbers and plans are sent to the LLM, never names or emails.

## Features

| Page | What it does |
|---|---|
| **Dashboard** | This month: spent vs plan per category, AI forecast total, categories needing attention, who paid, recent activity |
| **Expenses** | Add, edit, delete (amount, category, date, paid by, shared/personal, note); filter by month, category, member |
| **Budget** | Shared monthly limit per category (suggested from the last 3 months), spent vs limit, member agreement |
| **Forecast** | Same layout as the questionnaire demo: forecast, plan and last month per category, status chip, likely range, low-confidence flag, recommendation with 👍/👎 feedback, "adjust shared plan", group decision with "agrees" checkboxes, "show actual spending" for past months |
| **Activity** | Audit trail of every change (who added/changed what) |
| **Household** | Members and roles (owner / member / viewer), invite code, name and currency, CSV export, leave household, delete account |

Roles: **owner** manages members and settings; **member** adds expenses, edits own expenses, changes the plan and agrees;
**viewer** can only look. Changing the plan resets everyone's agreement for that month.

## How the forecast works (`backend/app/forecast.py`)

Each category uses **the model that was most accurate in the research evaluation** (lowest one-step-ahead RMSE on the
2024 test year, Assignment 3 Table V), with the orders selected on the 2023 validation year (Table IV):

| Category | Model |
|---|---|
| Housing | SARIMA(2,0,2)(0,1,1)12 |
| Transportation | SARIMA(2,1,2)(0,1,1)12 |
| Entertainment | SARIMA(1,1,0)(0,1,1)12 |
| Other | SARIMA(2,1,0)(0,1,1)12 |
| Utilities | ARIMA(2,1,2) |
| Healthcare | ARIMA(0,1,1) |
| Food | MA(3): mean of the previous 3 months |

- **One month ahead**, using only **completed months** before the selected month (the current, unfinished month is
  never counted). Forecasts are available up to one month after the last completed month.
- Models are **fitted on the household's own monthly totals** (re-estimated for each forecast month), with the COVID
  indicator (Apr–Dec 2020) when the history covers 2020.
- **Not enough history yet** (SARIMA needs 24 months, ARIMA 12): a simpler rule is used and marked *low confidence*:
  own average of the last 1–6 months, multiplied for SARIMA categories by the seasonal pattern of the national SARIMA
  fitted on the BLS dataset.
- **Range:** ± the household's own month-to-month variability (5–60%; ±35% with fewer than 3 months).
- **Total** = sum of the category forecasts.

Check: on the demo household the app's 2024 one-step RMSE matches the research results (e.g. Food 23.29 vs 23.29,
Healthcare 14.15 vs 14.14, Housing 58.30 vs 59.18); small differences come from re-fitting every month. Test FT-12 checks this.

## Tests (functional checklist and end-to-end check)

In `backend` with the environment active: `python -m pytest -v`

| Test | Checks |
|---|---|
| FT-01 | Register, log in, wrong password rejected, API requires login |
| FT-02 | Create household, join with invite code, roles |
| FT-03 | Permissions: viewer cannot add; member cannot delete others' expenses; outsiders cannot see the household |
| FT-04 | Expenses: validation (category, positive amount), filters |
| FT-05 | Shared plan and agreement; changing the plan resets agreement; viewer cannot agree |
| FT-06 | Forecast from one month of data: best model per category, range, low confidence; current month not counted; no forecast beyond next month |
| FT-07 | Recommendations without an LLM key (rule-based), disclaimer, feedback |
| FT-08 | Activity log records joins, expenses, plan and role changes |
| FT-09 | **End-to-end:** a member adds an expense → forecast updates → the same recommendation reaches all members |
| FT-10 | Demo household = research dataset exactly (Jan 2017 – Dec 2024), no fictional members, read-only; each category uses its best model |
| FT-11 | LLM reply is used; on failure the app falls back to rules |
| FT-12 | App reproduces the research evaluation: 2024 RMSE per category within 15% of Table V |

## Developing the interface (optional)

Needs Node.js 18+. Start the backend (`start.bat` / `start.sh`), then in `frontend`:
`npm install`, `npm run dev`, open http://localhost:5173. After changes run `npm run build` to update `frontend/dist`.

## Project structure

```
backend/app/       main.py (app), api.py (REST API), models.py (database), forecast.py (forecast engine),
                   recommend.py (LLM + rules), seed.py (demo households from the BLS dataset), security.py (passwords, tokens)
backend/data/      ce_monthly_2017_2024.csv (BLS monthly series from the research notebook)
backend/tests/     test_app.py (functional and end-to-end tests)
frontend/src/      React pages (Dashboard, Expenses, Budget, Forecast, Activity, Household)
frontend/dist/     built interface served by the backend
```

## Limitations

- Prototype for local use: no e-mail verification or password reset; SQLite file by default, PostgreSQL when DATABASE_URL is set.
- The demo household is the U.S. national average, which is smoother than one real household; its forecasts are therefore more accurate than forecasts for a single household will be.
- The seasonal pattern for short histories comes from U.S. data (BLS); Kazakhstani seasonality (e.g. Nauryz) is not yet included.
- Forecasts for one household are much less precise than for the national average; the app therefore shows ranges.
- Recommendations are decision support, not professional financial advice.
