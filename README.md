# SGAF — Sistema de Gestión de Activos Fijos

Desktop application for Colombian SMEs to manage fixed assets under NIIF para PYMEs standards. Built with Tauri 2 + React + Flask sidecar.

Automates depreciation calculations, generates audit-ready PDF reports, tracks maintenance events, and manages the complete asset lifecycle from acquisition through formal retirement (baja).

## Architecture

| Layer | Technology |
|-------|-----------|
| Desktop shell | Tauri 2 |
| Frontend | React 18 + TypeScript (strict) |
| Styling | Tailwind CSS v4 + shadcn/ui |
| State (server) | TanStack Query v5 |
| State (client) | Zustand |
| Routing | React Router v7 |
| Backend | Python 3.11 + Flask |
| Database | PostgreSQL (Supabase) via psycopg2 |
| PDF generation | ReportLab |
| Packaging | PyInstaller (Flask binary sidecar) |
| CI/CD | GitHub Actions |

## Features

### Asset Management
- Register fixed assets with full NIIF-compliant fields (code, category, historical cost, salvage value, useful life, depreciation method)
- Asset list with search and filtering
- Asset profile with edit history (full audit log)
- Formal retirement (baja) with protection against accidental deletion of active assets
- Photo attachments per asset
- Import fields: accounting code (PUC), characteristics, physical location

### Depreciation Engine (NIIF Sección 17)
- Three depreciation methods: Straight-Line (Línea Recta), Sum of Digits (Suma de Dígitos), Declining Balance (Saldo Decreciente)
- Monthly close dashboard showing period status and totals
- Per-asset depreciation schedule with historical results
- Support for legacy/imported assets with partial depreciation history

### PDF Reports
- Audit-ready monthly depreciation reports saved to a user-configured local folder
- Dashboard showing last generated report status and period

### Maintenance Tracking
- Log maintenance events per asset (open/closed lifecycle)
- View open events and full maintenance history per asset

### Configuration & Settings
- First-launch setup wizard (company name, NIT, logo, password, export folder)
- JWT-based authentication (token stored in memory only — never localStorage)
- Company settings and password update
- Per-category depreciation parameter defaults

### Bulk CSV Import
- CLI script to import legacy asset data from CSV
- Configurable depreciation parameters per asset category
- Supports assets with pre-existing accumulated depreciation

## Prerequisites

- Node.js 20+
- Python 3.11
- Rust stable (`rustup install stable`)
- A PostgreSQL database (Supabase or self-hosted)
- Linux: `libwebkit2gtk-4.1-dev`, `libgtk-3-dev`, `libayatana-appindicator3-dev`, `librsvg2-dev`

## Database Configuration

The app reads PostgreSQL credentials from a `db.conf` file at:

- **Linux/macOS**: `~/.local/share/com.sgaf.app/sgaf/db.conf`
- **Windows**: `%APPDATA%\com.sgaf.app\sgaf\db.conf`

Create the file with the following format:

```
PG_HOST=your-project.supabase.co
PG_PORT=5432
PG_USER=postgres
PG_PASS=your-password
PG_DB=postgres
```

The app will refuse to launch with a clear error message if the file is missing or any required key is absent.

## Development Setup

```bash
# 1. Install frontend dependencies
npm install

# 2. Set up Python virtual environment
cd src-python
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cd ..

# 3. Create db.conf with your PostgreSQL credentials (see Database Configuration above)

# 4. Build PyInstaller sidecar binary (required before tauri dev)
cd src-python
source .venv/bin/activate
pip install pyinstaller
pyinstaller sgaf.spec --distpath dist --workpath build

# Linux
cp dist/sgaf-backend ../src-tauri/binaries/sgaf-backend-x86_64-unknown-linux-gnu

# Windows
# cp dist/sgaf-backend.exe ../src-tauri/binaries/sgaf-backend-x86_64-pc-windows-msvc.exe
cd ..

# 5. Start development server
npm run tauri dev
```

## Running Tests

```bash
# Backend tests — requires live PostgreSQL databases
export TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/sgaf_test
export TEST_PRE_009_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/sgaf_pre009_test

cd src-python
source .venv/bin/activate
pytest --cov=app -v

# Frontend tests
npm run test

# Frontend tests (single run, no watch)
npm run test:run

# Frontend test coverage
npm run test:coverage
```

`TEST_DATABASE_URL` and `TEST_PRE_009_DATABASE_URL` must point to two separate, clean PostgreSQL databases. Tests are skipped automatically if these variables are not set.

## Bulk CSV Import

To import legacy fixed assets from a CSV file:

```bash
cd src-python
source .venv/bin/activate
python scripts/import_assets_csv.py --help
```

The script expects a CSV with columns matching the NIIF asset fields. See `scripts/import_assets_csv.py` for the expected format and options.

## Building for Production

```bash
npm run tauri build
```

Output locations:
- Linux AppImage: `src-tauri/target/release/bundle/appimage/*.AppImage`
- Windows MSI: `src-tauri/target/release/bundle/msi/*.msi`

## CI/CD

GitHub Actions runs on every push/PR to `main`:
1. **backend-tests**: pytest on `src-python/` (requires `TEST_DATABASE_URL` and `TEST_PRE_009_DATABASE_URL` secrets)
2. **frontend-tests**: Vitest on `src/`
3. **tauri-build**: builds Linux AppImage and Windows MSI (requires both test jobs to pass)

Artifacts are uploaded to each Actions run and retained for 30 days.

## Windows Validation (Manual Steps)

> Automated CI produces the `.msi`, but functional validation must be done manually on a physical Windows machine.

1. Download the `sgaf-installer-windows` artifact from the GitHub Actions run.
2. Run the `.msi` installer on a **clean Windows machine** (not a dev machine with Python/Node).
3. Create `%APPDATA%\com.sgaf.app\sgaf\db.conf` with valid PostgreSQL credentials.
4. After installation, double-click the SGAF shortcut.
5. Verify the app shell is visible within 15 seconds.
6. Confirm the setup wizard launches on first run.
7. Confirm there is **no blank/white window** at any point.

## Database Migrations

Schema versioning is handled through numbered SQL migration scripts in `src-python/migrations/`. The migration runner applies pending scripts automatically on app startup against the configured PostgreSQL database.

| Migration | Description |
|-----------|-------------|
| 001 | Initial schema |
| 002 | Seed default config |
| 003 | Logo path field |
| 004 | PDF tracking fields |
| 005 | Maintenance events schema |
| 006 | Maintenance closure fields |
| 007 | Remove estimated cost from maintenance |
| 008 | Asset categories config |
| 009 | Import fields (accounting code, characteristics, location) |
| 010 | Asset photos |
| 011 | Photos cascade index |

## Project Structure

```
sgaf/
├── src/                              # React frontend
│   ├── App.tsx                       # Backend-ready gating (loading/error/ready states)
│   ├── screens/                      # Top-level screens (Login, SetupWizard, Dashboard, DbSetup)
│   ├── features/
│   │   ├── assets/                   # AssetList, AssetForm, AssetDetail
│   │   ├── dashboard/                # Monthly close dashboard
│   │   ├── depreciation/             # Depreciation schedule and history
│   │   ├── maintenance/              # Maintenance event history
│   │   ├── reports/                  # PDF report generation UI
│   │   └── settings/                 # Company config and password
│   ├── components/
│   │   ├── layout/                   # AppLayout, Sidebar
│   │   ├── shared/                   # LoadingSpinner, ErrorMessage
│   │   └── ui/                       # shadcn/ui components
│   ├── hooks/                        # useAssets, useDepreciation, useMaintenance, useReports, etc.
│   ├── lib/                          # api.ts, queryClient.ts, tauri.ts, utils.ts
│   ├── store/                        # appStore.ts (Zustand: JWT token)
│   └── types/                        # asset.ts, depreciation.ts, maintenance.ts
├── src-tauri/                        # Tauri/Rust shell
│   ├── src/
│   │   ├── lib.rs                    # App entry, plugin init, sidecar spawn
│   │   ├── sidecar.rs                # Flask spawn, health poll, backend-ready/error events
│   │   ├── commands.rs               # get_app_data_path invoke command
│   │   └── db_config.rs              # Reads PostgreSQL credentials from db.conf
│   ├── tauri.conf.json               # App config, externalBin, bundle targets
│   └── capabilities/                 # Tauri v2 permissions
├── src-python/                       # Flask backend
│   ├── app/
│   │   ├── __init__.py               # create_app() factory + global JSON error handlers
│   │   ├── config.py                 # Config class (PG_HOST, PG_PORT, PG_USER, PG_PASS, PG_DB, FLASK_PORT)
│   │   ├── database.py               # SQLAlchemy engine (PostgreSQL) + migration runner
│   │   ├── middleware.py             # JWT auth middleware
│   │   ├── models/tables.py          # SQLAlchemy Core table definitions
│   │   ├── routes/                   # assets, auth, audit, config, depreciation, health, maintenance, photos, reports
│   │   ├── services/
│   │   │   ├── depreciation_engine.py  # NIIF depreciation calculation (all 3 methods)
│   │   │   └── pdf_generator.py        # ReportLab PDF report generation
│   │   ├── utils/                    # audit_logger, decimal_utils, file_utils
│   │   └── validators/               # asset_validator, maintenance_validator
│   ├── migrations/                   # Numbered SQL migration scripts (PostgreSQL)
│   ├── scripts/
│   │   └── import_assets_csv.py      # CLI bulk import tool
│   ├── tests/                        # pytest suite
│   ├── sgaf.spec                     # PyInstaller config
│   └── requirements*.txt
└── .github/workflows/
    └── build.yml                     # CI/CD pipeline
```

## Architecture Rules

- Flask always returns JSON — never HTML (global error handlers enforce this)
- No `float` for monetary values — use `Decimal` or integer cents; all monetary DB columns are TEXT
- Tauri `invoke()` for OS operations only; `fetch()` to Flask for all business logic
- JWT token stored in Zustand memory only — never `localStorage`/`sessionStorage`
- Window hidden until `backend-ready` event — never show a blank screen
- All timestamps stored as ISO 8601 UTC TEXT in PostgreSQL
- PostgreSQL credentials live exclusively in `db.conf` — never hardcoded or in env files checked into source control
