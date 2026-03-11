/**
 * AssetDetail — placeholder for Story 2.3.
 * Serves as the redirect target after a successful asset registration (AC3).
 * Full detail view, edit form, and change history will be implemented in Story 2.3.
 */

import { useNavigate, useParams } from "react-router-dom";

export default function AssetDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-2xl">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="mb-4 text-sm text-muted-foreground hover:text-foreground"
        >
          ← Volver
        </button>
        <h1 className="text-2xl font-bold text-foreground">Activo #{id}</h1>
        <p className="mt-2 text-muted-foreground">
          Detalle de activo en construcción (Story 2.3)
        </p>
      </div>
    </div>
  );
}
