import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { listen } from "@tauri-apps/api/event";
import ErrorMessage from "./components/shared/ErrorMessage";
import LoadingSpinner from "./components/shared/LoadingSpinner";
import { apiFetch, setApiPort } from "./lib/api";
import Login from "./screens/Login";
import SetupWizard from "./screens/SetupWizard";

type BackendStatus = "loading" | "ready" | "error";

function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("loading");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const navigate = useNavigate();

  useEffect(() => {
    // Listen for backend lifecycle events emitted by sidecar.rs (AC2, AC3)
    const unlistenReady = listen<number>("backend-ready", (event) => {
      setApiPort(event.payload);
      setBackendStatus("ready");
    });

    const unlistenError = listen<string>("backend-error", (event) => {
      setBackendStatus("error");
      setErrorMessage(event.payload);
    });

    return () => {
      unlistenReady.then((f) => f());
      unlistenError.then((f) => f());
    };
  }, []);

  // Once backend is ready, check if first-launch setup has been completed (AC1, AC6)
  useEffect(() => {
    if (backendStatus !== "ready") return;
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

  if (backendStatus === "error") {
    return (
      <ErrorMessage
        message={errorMessage}
        hint="Verifica que la aplicación se instaló correctamente y vuelve a intentar."
      />
    );
  }

  return (
    <Routes>
      <Route path="/wizard" element={<SetupWizard />} />
      <Route path="/login" element={<Login />} />
      <Route path="/*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default App;
