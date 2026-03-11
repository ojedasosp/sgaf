/**
 * Dashboard — post-login landing page.
 * Story 2.2: Navigation links to Activos list and registration added.
 * Future epics will build the full depreciation panel and sidebar here.
 */

import { useNavigate } from "react-router-dom";

export default function Dashboard() {
  const navigate = useNavigate();

  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-foreground">SGAF</h1>
        <p className="mt-2 text-muted-foreground">
          Sistema de Gestión de Activos Fijos
        </p>
        <div className="mt-6 flex flex-col items-center gap-3">
          <button
            type="button"
            onClick={() => navigate("/assets")}
            className="rounded-md bg-[#458588] px-6 py-2 text-sm font-medium text-white hover:bg-[#458588]/90"
          >
            Ver Activos
          </button>
          <button
            type="button"
            onClick={() => navigate("/assets/new")}
            className="rounded-md border border-[#458588] px-6 py-2 text-sm font-medium text-[#458588] hover:bg-[#458588]/10"
          >
            + Nuevo Activo
          </button>
        </div>
      </div>
    </div>
  );
}
