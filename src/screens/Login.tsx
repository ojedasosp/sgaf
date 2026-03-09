/**
 * Login screen — placeholder for Story 1.4.
 *
 * Story 1.4 will implement:
 * - Password field + "Ingresar" button
 * - POST /api/v1/auth/login → JWT stored in Zustand (memory only)
 * - require_auth middleware on all protected Flask routes
 * - Redirect to dashboard on success
 */
export default function Login() {
  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-8 shadow-sm text-center">
        <h1 className="text-2xl font-bold text-foreground">SGAF</h1>
        <p className="mt-2 text-muted-foreground">
          Sistema de Gestión de Activos Fijos
        </p>
        <p className="mt-4 text-sm text-green-600">
          Setup complete. Login coming in Story 1.4.
        </p>
      </div>
    </div>
  );
}
