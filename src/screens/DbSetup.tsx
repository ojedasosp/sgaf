import { useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";

interface DbSetupProps {
  /** Ref owned by App.tsx — set to false when this component handles a backend-error inline */
  dbSetupActiveRef: React.MutableRefObject<boolean>;
}

interface FormValues {
  host: string;
  port: string;
  user: string;
  pass: string;
  db: string;
}

interface FormErrors {
  host?: string;
  port?: string;
  user?: string;
  pass?: string;
  db?: string;
  submit?: string;
}

function validate(values: FormValues): FormErrors {
  const errs: FormErrors = {};
  if (!values.host.trim()) errs.host = "Requerido";
  if (!values.user.trim()) errs.user = "Requerido";
  if (!values.pass.trim()) errs.pass = "Requerido";
  if (!values.db.trim()) errs.db = "Requerido";
  const portNum = parseInt(values.port, 10);
  if (!values.port.trim() || isNaN(portNum) || portNum < 1 || portNum > 65535) {
    errs.port = "Puerto inválido (1-65535)";
  }
  return errs;
}

export default function DbSetup({ dbSetupActiveRef }: DbSetupProps) {
  const [values, setValues] = useState<FormValues>({
    host: "",
    port: "5432",
    user: "",
    pass: "",
    db: "",
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [isConnecting, setIsConnecting] = useState(false);
  const isConnectingRef = useRef(false);

  // Listen for backend-error while we're waiting for a connection attempt
  useEffect(() => {
    const unlisten = listen<string>("backend-error", (event) => {
      if (!isConnectingRef.current) return;
      isConnectingRef.current = false;
      dbSetupActiveRef.current = true; // Stay in db-setup mode
      setIsConnecting(false);
      setErrors({ submit: event.payload });
    });
    return () => {
      unlisten.then((f) => f());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleChange(field: keyof FormValues) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setValues((prev) => ({ ...prev, [field]: e.target.value }));
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate(values);
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
    setErrors({});
    setIsConnecting(true);
    isConnectingRef.current = true;

    try {
      await invoke("save_db_config", {
        host: values.host.trim(),
        port: values.port.trim(),
        user: values.user.trim(),
        pass: values.pass,
        db: values.db.trim(),
      });
      // Kick off backend — App.tsx listens for backend-ready / backend-error
      invoke("retry_backend");
    } catch (err) {
      isConnectingRef.current = false;
      setIsConnecting(false);
      setErrors({
        submit: err instanceof Error ? err.message : "Error al guardar la configuración.",
      });
    }
  }

  if (isConnecting) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-sm text-muted-foreground">Conectando al servidor...</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-8 shadow-sm">
        <h2 className="mb-2 text-2xl font-bold text-foreground">
          Configurar Base de Datos
        </h2>
        <p className="mb-6 text-sm text-muted-foreground">
          Ingresa los parámetros de conexión al servidor PostgreSQL.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Host */}
          <div>
            <label htmlFor="db-host" className="mb-1 block text-sm font-medium text-foreground">
              Host <span className="text-destructive">*</span>
            </label>
            <input
              id="db-host"
              type="text"
              value={values.host}
              onChange={handleChange("host")}
              placeholder="db.ejemplo.com"
              autoComplete="off"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.host && <p className="mt-1 text-xs text-destructive">{errors.host}</p>}
          </div>

          {/* Port */}
          <div>
            <label htmlFor="db-port" className="mb-1 block text-sm font-medium text-foreground">
              Puerto <span className="text-destructive">*</span>
            </label>
            <input
              id="db-port"
              type="text"
              value={values.port}
              onChange={handleChange("port")}
              placeholder="5432"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.port && <p className="mt-1 text-xs text-destructive">{errors.port}</p>}
          </div>

          {/* User */}
          <div>
            <label htmlFor="db-user" className="mb-1 block text-sm font-medium text-foreground">
              Usuario <span className="text-destructive">*</span>
            </label>
            <input
              id="db-user"
              type="text"
              value={values.user}
              onChange={handleChange("user")}
              placeholder="sgaf_user"
              autoComplete="username"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.user && <p className="mt-1 text-xs text-destructive">{errors.user}</p>}
          </div>

          {/* Password */}
          <div>
            <label htmlFor="db-pass" className="mb-1 block text-sm font-medium text-foreground">
              Contraseña <span className="text-destructive">*</span>
            </label>
            <input
              id="db-pass"
              type="password"
              value={values.pass}
              onChange={handleChange("pass")}
              autoComplete="current-password"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.pass && <p className="mt-1 text-xs text-destructive">{errors.pass}</p>}
          </div>

          {/* Database name */}
          <div>
            <label htmlFor="db-name" className="mb-1 block text-sm font-medium text-foreground">
              Nombre de base de datos <span className="text-destructive">*</span>
            </label>
            <input
              id="db-name"
              type="text"
              value={values.db}
              onChange={handleChange("db")}
              placeholder="sgaf_production"
              autoComplete="off"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.db && <p className="mt-1 text-xs text-destructive">{errors.db}</p>}
          </div>

          {/* Submit error */}
          {errors.submit && (
            <div className="rounded-md border border-destructive/20 bg-destructive/5 p-3">
              <p className="text-sm text-destructive">{errors.submit}</p>
            </div>
          )}

          <div className="pt-2">
            <button
              type="submit"
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              Conectar
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
