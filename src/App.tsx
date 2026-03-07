import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import LoadingSpinner from "./components/shared/LoadingSpinner";
import ErrorMessage from "./components/shared/ErrorMessage";
import { setApiPort } from "./lib/api";

type BackendStatus = "loading" | "ready" | "error";

function App() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("loading");
  const [errorMessage, setErrorMessage] = useState<string>("");

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

  // App shell — authenticated routes will be rendered here in later stories (1.3, 1.4)
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-foreground">SGAF</h1>
        <p className="mt-2 text-muted-foreground">
          Sistema de Gestión de Activos Fijos
        </p>
        <p className="mt-1 text-sm text-green-600">Backend activo ✓</p>
      </div>
    </div>
  );
}

export default App;
