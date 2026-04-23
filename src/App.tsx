import { useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import ErrorMessage from "./components/shared/ErrorMessage";
import LoadingSpinner from "./components/shared/LoadingSpinner";
import { apiFetch, setApiPort } from "./lib/api";
import { useAppStore } from "./store/appStore";
import AssetDetail from "./features/assets/AssetDetail";
import AssetForm from "./features/assets/AssetForm";
import AssetList from "./features/assets/AssetList";
import DepreciationPage from "./features/depreciation/DepreciationPage";
import ReportsPage from "./features/reports/ReportsPage";
import SettingsPage from "./features/settings/SettingsPage";
import Dashboard from "./screens/Dashboard";
import DbSetup from "./screens/DbSetup";
import Login from "./screens/Login";
import SetupWizard from "./screens/SetupWizard";

type BackendStatus = "loading" | "ready" | "error" | "db-setup";

/** Redirects to /login if no JWT token is present in the Zustand store. */
function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAppStore((s) => s.token);
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}

function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("loading");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const navigate = useNavigate();
  const initialRouteResolved = useRef(false);
  // When true, DbSetup handles backend-error inline — App.tsx must not switch to "error"
  const dbSetupActiveRef = useRef(false);

  useEffect(() => {
    // Listen for backend lifecycle events emitted by sidecar.rs
    const unlistenReady = listen<number>("backend-ready", (event) => {
      dbSetupActiveRef.current = false;
      setApiPort(event.payload);
      setBackendStatus("ready");
    });

    const unlistenError = listen<string>("backend-error", (event) => {
      if (dbSetupActiveRef.current) return; // DbSetup handles error inline
      setBackendStatus("error");
      setErrorMessage(event.payload);
    });

    const unlistenDbSetup = listen("db-setup-required", () => {
      dbSetupActiveRef.current = true;
      setBackendStatus("db-setup");
    });

    // Poll backend status in case the event fired before this listener registered.
    // This handles the race condition where the sidecar starts faster than React mounts.
    invoke<{ Loading?: null; Ready?: number; Error?: string } | string>(
      "get_backend_status",
    )
      .then((state) => {
        if (state === "SetupRequired") {
          dbSetupActiveRef.current = true;
          setBackendStatus("db-setup");
          return;
        }
        if (typeof state === "object") {
          if ("Ready" in state && state.Ready != null) {
            setApiPort(state.Ready);
            setBackendStatus("ready");
          } else if ("Error" in state && state.Error != null) {
            setBackendStatus("error");
            setErrorMessage(state.Error);
          }
        }
        // "Loading" — wait for the event
      })
      .catch(() => {
        // Command not available (e.g., running outside Tauri) — ignore
      });

    return () => {
      unlistenReady.then((f) => f());
      unlistenError.then((f) => f());
      unlistenDbSetup.then((f) => f());
    };
  }, []);

  // Once backend is ready, check if first-launch setup has been completed (AC1, AC6)
  // Runs only once — subsequent route changes must not re-trigger this.
  useEffect(() => {
    if (backendStatus !== "ready") return;
    if (initialRouteResolved.current) return;
    initialRouteResolved.current = true;
    apiFetch<{ data: { setup_complete: boolean } }>("/config/setup-status")
      .then(({ data }) => {
        navigate(data.setup_complete ? "/login" : "/wizard", { replace: true });
      })
      .catch(() => {
        // If setup-status fails, default to wizard (safe fallback)
        navigate("/wizard", { replace: true });
      });
  }, [backendStatus, navigate]);

  if (backendStatus === "loading") {
    return <LoadingSpinner message="Iniciando SGAF..." />;
  }

  if (backendStatus === "db-setup") {
    return <DbSetup dbSetupActiveRef={dbSetupActiveRef} />;
  }

  if (backendStatus === "error") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-8">
        <ErrorMessage
          message={errorMessage}
          hint="Verifica las credenciales en db.conf y la conectividad de red."
        />
        <button
          onClick={async () => {
            await invoke("reset_db_config");
            setBackendStatus("loading");
            invoke("retry_backend");
          }}
          className="text-sm text-primary underline hover:opacity-80"
        >
          Reconfigurar conexión a base de datos
        </button>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/wizard" element={<SetupWizard />} />
      <Route path="/login" element={<Login />} />
      <Route
        path="/dashboard"
        element={
          <PrivateRoute>
            <Dashboard />
          </PrivateRoute>
        }
      />
      <Route
        path="/assets"
        element={
          <PrivateRoute>
            <AssetList />
          </PrivateRoute>
        }
      />
      <Route
        path="/assets/new"
        element={
          <PrivateRoute>
            <AssetForm />
          </PrivateRoute>
        }
      />
      <Route
        path="/assets/:id"
        element={
          <PrivateRoute>
            <AssetDetail />
          </PrivateRoute>
        }
      />
      <Route
        path="/depreciation"
        element={
          <PrivateRoute>
            <DepreciationPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/reports"
        element={
          <PrivateRoute>
            <ReportsPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <PrivateRoute>
            <SettingsPage />
          </PrivateRoute>
        }
      />
      <Route path="/*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default App;
