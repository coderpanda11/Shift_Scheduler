# Dynamic Shift Scheduling and Duty Roster Management System

A local web application for DC/In-Charge staff to generate fair monthly duty rosters, regenerate them when availability changes, and maintain versioned schedule history.

## Quick start

```bash
cd shift_scheduler
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

## What it does

- Manages employees (Non-Executives, Backup, Trainee Engineers)
- Configures working calendar, weekends, and holidays
- Records availability / leave
- Generates **fair, balanced** monthly rosters using a deterministic weighted algorithm
- Regenerates schedules when staff become unavailable (new version, old preserved)
- Supports manual overrides with audit trail
- Exports roster to CSV, Excel (Roster + Duty Summary), and print-friendly HTML

## Architecture

```
app.py              → Streamlit UI entry + sidebar router
views/              → Page modules (dashboard, generate, employees, …)
services/           → Business logic (DB transactions)
scheduler/          → Scheduling engine (no Streamlit imports)
models.py           → SQLAlchemy ORM
database.py         → Init, seed, sessions
config.py           → Default rules/weights
data/scheduler.db   → SQLite database (auto-created)
```

The scheduling engine is isolated so it can later be replaced with OR-Tools CP-SAT without changing the UI.

## Staff & shift structure

| Role | Shifts |
|------|--------|
| Non-Executive (primary) | 1st/2nd/3rd primary slots |
| Non-Executive Backup | 3rd primary only when a primary NE is unavailable |
| Trainee Engineer | 1st/2nd trainee slots; may cover 2nd **primary** during NE shortage; **never 3rd** |

**Working day:** 2nd + 3rd shifts (+ trainee on 1st/2nd).  
**Non-working day:** 1st + 2nd + 3rd (+ trainees on 1st/2nd).

Paired display: 1st and 2nd shift cells show `Non-Executive + (Trainee)`.

## Scheduling rules

### Hard constraints (must pass to publish)

1. Inactive / unavailable employees cannot be assigned
2. One employee, one assignment per date
3. No duplicate employee on same shift
4. Trainees never on 3rd shift
5. Backup not used in IDEAL mode (all primary NEs available all month)
6. Every required slot must be filled

### Soft constraints (warnings; publish allowed with confirmation)

1. Balance total duties among primary NEs (target max−min ≤ 1)
2. Balance 2nd vs 3rd counts independently
3. Balance non-working-day duties, especially 1st shift
4. Balance trainee slot counts
5. Avoid 3rd shift followed by 1st shift next day
6. Avoid excessive consecutive 3rd shifts (default max 2)
7. Optional cross-month fairness tie-break

### Priority when rules conflict

Availability → coverage → rest/safety → role → fair totals → fair shift mix

### Scheduling modes

- **IDEAL:** All primary Non-Executives available entire month → Backup unused
- **BACKUP / REBALANCED:** Any primary NE unavailable → full re-run; Backup covers 3rd; Trainees may cover 2nd primary

## How fairness is calculated

For each empty slot, eligible employees are scored (lower = better):

```
score = total_duties×W_TOTAL + same_shift×W_SAME + non_working×W_NWD
      + first_shift×W_FIRST + consecutive_third_penalty + recent_duty×W_RECENT
      + backup/role penalties
```

Tie-break: fewest duties → longest since last duty → lowest employee ID.

Weights are configurable in **Settings → Scheduling Rules**.

## Schedule versions

Each generation creates a new version (`v1`, `v2`, …). Old versions are never overwritten. Statuses: `draft`, `published`, `archived`. Assignments store employee name/role snapshots for historical accuracy.

## Tests

```bash
pytest tests/ -v
```

Covers ideal scheduling, backup activation, availability, month lengths, holidays, versioning, manual override audit, and trainee rebalance.

## Reset development database

Delete `data/scheduler.db` and restart the app — tables and seed data are recreated automatically.

## Offline / intranet installation (no internet)

Target OS: **Windows** or **Linux** (Ubuntu/Kali). Python 3.11+ must be installed on the target machine first.

### Step 1 — On a PC with internet

```bash
cd shift_scheduler
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip download -r requirements.txt -d vendor
```

Copy the entire `shift_scheduler` folder (including `vendor/`) to USB or network share.

### Step 2 — On the offline PC

```bash
cd shift_scheduler
python -m venv .venv
.venv\Scripts\activate
pip install --no-index --find-links=vendor -r requirements.txt
streamlit run app.py
```

### Intranet access (Linux)

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Restrict access via OS firewall to your office subnet. Windows users on the same LAN can browse to `http://<server-ip>:8501`.

### Optional server deployment

On an internal VM: install Python, copy project + `vendor/`, create venv, install offline packages, run Streamlit bound to private IP. Optional reverse proxy (nginx/IIS) in front — not required for local use.

## Seed data

First run creates placeholder staff: Non-Executive 1–3, Non-Executive Backup, Trainee Engineer 1–4. All names are editable from the UI.

## License

Internal use — BDL Projects.
