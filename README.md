# SGAF — Sistema de Gestión de Activos Fijos

Desktop application built with Tauri 2 + React + Flask sidecar for fixed asset management with IFRS/NIIF depreciation.

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
| Database | SQLite (WAL mode) |
| Packaging | PyInstaller (Flask binary sidecar) |
| CI/CD | GitHub Actions |

## Prerequisites

- Node.js 20+
- Python 3.11
- Rust stable (`rustup install stable`)
- Linux: `libwebkit2gtk-4.1-dev`, `libgtk-3-dev`, `libayatana-appindicator3-dev`, `librsvg2-dev`

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

# 3. Build PyInstaller sidecar binary (required before tauri dev)
cd src-python
source .venv/bin/activate
pip install pyinstaller
pyinstaller sgaf.spec --distpath dist --workpath build

# Linux
cp dist/sgaf-backend ../src-tauri/binaries/sgaf-backend-x86_64-unknown-linux-gnu

# Windows
# cp dist/sgaf-backend.exe ../src-tauri/binaries/sgaf-backend-x86_64-pc-windows-msvc.exe
cd ..

# 4. Start development server
npm run tauri dev
```

## Running Tests

```bash
# Backend tests
cd src-python
source .venv/bin/activate
pytest --cov=app -v

# Frontend tests
npm run test

# Frontend tests (single run, no watch)
npm run test:run
```

## Building for Production

```bash
npm run tauri build
```

Output locations:
- Linux AppImage: `src-tauri/target/release/bundle/appimage/*.AppImage`
- Windows MSI: `src-tauri/target/release/bundle/msi/*.msi`

## CI/CD

GitHub Actions runs on every push/PR to `main`:
1. **backend-tests**: pytest on `src-python/`
2. **frontend-tests**: Vitest on `src/`
3. **tauri-build**: builds Linux AppImage and Windows MSI (requires both test jobs to pass)

Artifacts are uploaded to each Actions run and retained for 30 days.

## Windows Validation (Manual Steps)

> AC6 requires a physical Windows machine or VM. Automated CI produces the `.msi`, but functional validation must be done manually.

1. Download the `sgaf-installer-windows` artifact from the GitHub Actions run.
2. Run the `.msi` installer on a **clean Windows machine** (not a dev machine with Python/Node).
3. After installation, double-click the SGAF shortcut.
4. Verify the app shell is visible within **15 seconds** (NFR3).
5. Confirm the loading spinner appears during startup and the "Backend activo" message appears.
6. Confirm there is **no blank/white window** at any point (NFR15).

## Project Structure

```
sgaf/
├── src/                    # React frontend
│   ├── App.tsx             # Backend-ready gating (loading/error/ready states)
│   ├── components/shared/  # LoadingSpinner, ErrorMessage
│   ├── lib/                # api.ts, queryClient.ts, tauri.ts
│   └── store/              # appStore.ts (Zustand: token)
├── src-tauri/              # Tauri/Rust shell
│   ├── src/
│   │   ├── lib.rs          # App entry, plugin init, sidecar spawn
│   │   ├── sidecar.rs      # Flask spawn, health poll, backend-ready/error events
│   │   └── commands.rs     # get_app_data_path invoke command
│   ├── tauri.conf.json     # App config, externalBin, bundle targets
│   └── capabilities/       # Tauri v2 permissions
├── src-python/             # Flask backend
│   ├── app/
│   │   ├── __init__.py     # create_app() factory + global JSON error handlers
│   │   ├── config.py       # Config class (DB path, port)
│   │   └── routes/
│   │       └── health.py   # GET /api/v1/health
│   ├── tests/              # pytest suite
│   ├── sgaf.spec           # PyInstaller config
│   └── requirements*.txt
└── .github/workflows/
    └── build.yml           # CI/CD pipeline
```

## Architecture Rules

- Flask always returns JSON — never HTML (global error handlers enforce this)
- No `float` for numeric values — use `Decimal` or integer cents
- Tauri `invoke()` for OS operations only; `fetch()` to Flask for business logic
- JWT token stored in Zustand memory only — never `localStorage`/`sessionStorage`
- Window hidden until `backend-ready` event — never show a blank screen
