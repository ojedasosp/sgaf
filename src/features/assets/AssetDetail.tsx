/**
 * AssetDetail — Full implementation for Story 2.3.
 *
 * Modes:
 *   view  — display all asset fields in grouped sections + audit history
 *   edit  — pre-populated form with all 8 editable fields; PATCH on save
 *
 * Layout:
 *   - Back button → /assets
 *   - Page title: "<code> — <description>"
 *   - Profile section (Identificación + Valorización + Estado)
 *   - "Editar" button → switches to edit mode
 *   - Historial de Cambios section (audit log table)
 *
 * Color system: Gruvbox Light (matches AssetList.tsx and AssetForm.tsx)
 */

import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { useGetAssetAuditLog } from "../../hooks/useAuditLog";
import { useDeleteAsset, useGetAsset, useRetireAsset, useUpdateAsset } from "../../hooks/useAssets";
import type {
  AuditLogEntry,
  Asset,
  AssetStatus,
  DepreciationMethod,
  RetireAssetPayload,
  UpdateAssetPayload,
} from "../../types/asset";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<AssetStatus, { label: string; className: string }> = {
  active: {
    label: "Activo",
    className: "bg-[#98971a]/10 text-[#98971a] border-[#98971a]/20",
  },
  in_maintenance: {
    label: "En Mantenimiento",
    className: "bg-[#d79921]/10 text-[#d79921] border-[#d79921]/20",
  },
  retired: {
    label: "Retirado",
    className: "bg-[#7c6f64]/10 text-[#7c6f64] border-[#7c6f64]/20",
  },
};

const METHOD_LABELS: Record<DepreciationMethod, string> = {
  straight_line: "Lineal",
  sum_of_digits: "Suma de Dígitos",
  declining_balance: "Saldo Decreciente",
};

const DEPRECIATION_OPTIONS: { value: DepreciationMethod; label: string }[] = [
  { value: "straight_line", label: "Lineal" },
  { value: "sum_of_digits", label: "Suma de Dígitos" },
  { value: "declining_balance", label: "Saldo Decreciente" },
];

const ACTION_LABELS: Record<string, string> = {
  CREATE: "Creación",
  UPDATE: "Edición",
  RETIRE: "Baja",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

function formatDateTime(isoUtc: string): string {
  if (!isoUtc) return "—";
  const d = new Date(isoUtc);
  return d.toLocaleString("es-CO", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: AssetStatus }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.active;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${cfg.className}`}
    >
      {cfg.label}
    </span>
  );
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-2 sm:flex-row sm:gap-4">
      <dt className="w-full text-sm font-medium text-[#665c54] sm:w-44 sm:shrink-0">{label}</dt>
      <dd className="text-sm text-[#3c3836]">{value}</dd>
    </div>
  );
}

function ProfileSkeleton() {
  const bar = (w: string) => (
    <div className={`h-4 animate-pulse rounded bg-[#d5c4a1] ${w}`} />
  );
  return (
    <div className="space-y-3 p-6">
      {[...Array(8)].map((_, i) => (
        <div key={i} className="flex gap-4">
          <div className="h-4 w-36 animate-pulse rounded bg-[#d5c4a1]" />
          {bar(i % 2 === 0 ? "w-48" : "w-64")}
        </div>
      ))}
    </div>
  );
}

function AuditSkeleton() {
  return (
    <div className="space-y-2 p-4">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="flex gap-3">
          <div className="h-4 w-32 animate-pulse rounded bg-[#d5c4a1]" />
          <div className="h-4 w-20 animate-pulse rounded bg-[#d5c4a1]" />
          <div className="h-4 w-28 animate-pulse rounded bg-[#d5c4a1]" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edit form types and helpers
// ---------------------------------------------------------------------------

interface EditFormValues {
  code: string;
  description: string;
  category: string;
  historical_cost: string;
  salvage_value: string;
  useful_life_months: string;
  acquisition_date: string;
  depreciation_method: DepreciationMethod;
}

interface EditFormErrors {
  code?: string;
  description?: string;
  category?: string;
  historical_cost?: string;
  salvage_value?: string;
  useful_life_months?: string;
  acquisition_date?: string;
  depreciation_method?: string;
  submit?: string;
}

function assetToFormValues(asset: Asset): EditFormValues {
  return {
    code: asset.code,
    description: asset.description,
    category: asset.category,
    historical_cost: asset.historical_cost,
    salvage_value: asset.salvage_value,
    useful_life_months: String(asset.useful_life_months),
    acquisition_date: asset.acquisition_date,
    depreciation_method: asset.depreciation_method,
  };
}

function validateEditField(
  field: keyof EditFormValues,
  values: EditFormValues
): string | undefined {
  const value = values[field];
  const strVal = String(value).trim();

  switch (field) {
    case "code":
      if (!strVal) return "El código del activo es obligatorio";
      break;
    case "description":
      if (!strVal) return "La descripción es obligatoria";
      break;
    case "category":
      if (!strVal) return "La categoría es obligatoria";
      break;
    case "historical_cost": {
      if (!strVal) return "El costo histórico es obligatorio";
      const n = Number(strVal);
      if (isNaN(n)) return "El costo histórico debe ser un número válido";
      if (n <= 0) return "El costo histórico debe ser mayor a 0";
      break;
    }
    case "salvage_value": {
      if (strVal === "") return "El valor residual es obligatorio";
      const sv = Number(strVal);
      if (isNaN(sv)) return "El valor residual debe ser un número válido";
      if (sv < 0) return "El valor residual debe ser cero o mayor";
      const hc = Number(String(values.historical_cost).trim());
      if (!isNaN(hc) && hc > 0 && sv >= hc)
        return "El valor residual debe ser menor al costo histórico";
      break;
    }
    case "useful_life_months": {
      if (!strVal) return "La vida útil es obligatoria";
      const months = Number(strVal);
      if (!Number.isInteger(months) || isNaN(months))
        return "La vida útil debe ser un número entero";
      if (months <= 0) return "La vida útil debe ser mayor a 0";
      break;
    }
    case "acquisition_date": {
      if (!strVal) return "La fecha de adquisición es obligatoria";
      const iso = /^\d{4}-\d{2}-\d{2}$/.test(strVal);
      if (!iso) return "Formato de fecha inválido (use AAAA-MM-DD)";
      const d = new Date(strVal);
      if (isNaN(d.getTime())) return "Fecha inválida";
      break;
    }
    case "depreciation_method":
      if (!strVal) return "El método de depreciación es obligatorio";
      break;
  }
  return undefined;
}

function validateAllEditFields(values: EditFormValues): EditFormErrors {
  const errors: EditFormErrors = {};
  const fields: (keyof EditFormValues)[] = [
    "code",
    "description",
    "category",
    "historical_cost",
    "salvage_value",
    "useful_life_months",
    "acquisition_date",
    "depreciation_method",
  ];
  for (const field of fields) {
    const err = validateEditField(field, values);
    if (err) errors[field] = err;
  }
  return errors;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AssetDetail() {
  const { id } = useParams<{ id: string }>();
  const assetId = Number(id);
  const navigate = useNavigate();

  const {
    data: asset,
    isLoading: assetLoading,
    isError: assetError,
    refetch: refetchAsset,
  } = useGetAsset(assetId);

  const {
    data: auditLog,
    isLoading: auditLoading,
  } = useGetAssetAuditLog(assetId);

  const { mutate: updateAsset, isPending: isUpdating } = useUpdateAsset();
  const { mutate: retireAsset, isPending: isRetirePending } = useRetireAsset();
  const { mutate: deleteAsset, isPending: isDeletePending } = useDeleteAsset();

  // Edit mode state
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [editValues, setEditValues] = useState<EditFormValues | null>(null);
  const [editErrors, setEditErrors] = useState<EditFormErrors>({});
  const [editTouched, setEditTouched] = useState<
    Partial<Record<keyof EditFormValues, boolean>>
  >({});

  // Retire mode state
  const [isRetiring, setIsRetiring] = useState(false);
  const [retireDate, setRetireDate] = useState(new Date().toISOString().slice(0, 10));
  const [retireError, setRetireError] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  // ---------------------------------------------------------------------------
  // Edit mode handlers
  // ---------------------------------------------------------------------------

  function handleEnterEdit() {
    if (!asset) return;
    setEditValues(assetToFormValues(asset));
    setEditErrors({});
    setEditTouched({});
    setIsRetiring(false);
    setShowDeleteConfirm(false);
    setDeleteError("");
    setMode("edit");
  }

  function handleCancelEdit() {
    if (!editValues || !asset) {
      setMode("view");
      return;
    }
    const original = assetToFormValues(asset);
    const isDirty = (Object.keys(editValues) as (keyof EditFormValues)[]).some(
      (k) => editValues[k] !== original[k]
    );
    if (isDirty) {
      if (!window.confirm("¿Descartar cambios? Los datos ingresados se perderán.")) return;
    }
    setMode("view");
  }

  function handleEditChange(field: keyof EditFormValues, value: string) {
    setEditValues((prev) => (prev ? { ...prev, [field]: value } : prev));
    if (editErrors[field]) {
      setEditErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  }

  function handleEditBlur(field: keyof EditFormValues) {
    setEditTouched((prev) => ({ ...prev, [field]: true }));
    if (!editValues) return;
    const err = validateEditField(field, editValues);
    setEditErrors((prev) => ({ ...prev, [field]: err }));
  }

  function handleEditSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!editValues || !asset) return;

    const allTouched = Object.fromEntries(
      Object.keys(editValues).map((k) => [k, true])
    ) as Record<keyof EditFormValues, boolean>;
    setEditTouched(allTouched);

    const allErrors = validateAllEditFields(editValues);
    if (Object.keys(allErrors).length > 0) {
      setEditErrors(allErrors);
      const firstField = Object.keys(allErrors)[0] as keyof EditFormValues;
      document.getElementById(firstField)?.focus();
      return;
    }

    setEditErrors({});

    const payload: UpdateAssetPayload = {
      code: editValues.code.trim(),
      description: editValues.description.trim(),
      category: editValues.category.trim(),
      historical_cost: editValues.historical_cost.trim(),
      salvage_value: editValues.salvage_value.trim(),
      useful_life_months: parseInt(editValues.useful_life_months, 10),
      acquisition_date: editValues.acquisition_date,
      depreciation_method: editValues.depreciation_method,
    };

    updateAsset(
      { id: assetId, payload },
      {
        onSuccess: () => {
          setMode("view");
        },
        onError: (err) => {
          const message = err instanceof Error ? err.message : "Error al guardar los cambios";
          if (err instanceof ApiError && err.field && editValues && err.field in editValues) {
            const field = err.field as keyof EditFormValues;
            setEditErrors((prev) => ({ ...prev, [field]: message }));
            setEditTouched((prev) => ({ ...prev, [field]: true }));
            document.getElementById(field)?.focus();
          } else {
            setEditErrors({ submit: message });
          }
        },
      }
    );
  }

  // ---------------------------------------------------------------------------
  // Retire mode handlers
  // ---------------------------------------------------------------------------

  function handleEnterRetire() {
    if (mode === "edit") return; // guard: cannot retire while editing
    setRetireDate(new Date().toISOString().slice(0, 10));
    setRetireError("");
    setShowDeleteConfirm(false);
    setIsRetiring(true);
  }

  function handleCancelRetire() {
    setIsRetiring(false);
    setRetireError("");
  }

  function handleRetireSubmit() {
    const payload: RetireAssetPayload = { retirement_date: retireDate };
    retireAsset(
      { id: assetId, payload },
      {
        onSuccess: () => {
          setIsRetiring(false);
          setRetireError("");
        },
        onError: (err) => {
          setRetireError(
            err instanceof ApiError ? err.message : "No se pudo dar de baja el activo."
          );
        },
      }
    );
  }

  function handleDeleteClick() {
    setShowDeleteConfirm(true);
    setDeleteError("");
  }

  function handleDeleteCancel() {
    setShowDeleteConfirm(false);
    setDeleteError("");
  }

  function handleDeleteConfirm() {
    deleteAsset(assetId, {
      onSuccess: () => navigate("/assets"),
      onError: (err) => {
        setShowDeleteConfirm(false);
        setDeleteError(
          err instanceof ApiError ? err.message : "No se puede eliminar el activo."
        );
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Field helpers for edit form
  // ---------------------------------------------------------------------------

  function fieldClass(field: keyof EditFormValues): string {
    const base =
      "mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring";
    return editErrors[field] && editTouched[field]
      ? `${base} border-[#cc241d]`
      : `${base} border-[#bdae93]`;
  }

  function showError(field: keyof EditFormValues) {
    return editTouched[field] && editErrors[field] ? (
      <p className="mt-1 text-xs text-[#cc241d]" role="alert">
        {editErrors[field]}
      </p>
    ) : null;
  }

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  if (assetLoading) {
    return (
      <div className="min-h-screen bg-background p-6">
        <div className="mx-auto max-w-3xl">
          <div className="mb-4 h-4 w-24 animate-pulse rounded bg-[#d5c4a1]" />
          <div className="mb-6 h-8 w-64 animate-pulse rounded bg-[#d5c4a1]" />
          <div className="rounded-lg border border-border bg-[#f2e5bc] p-6">
            <ProfileSkeleton />
          </div>
        </div>
      </div>
    );
  }

  if (assetError || !asset) {
    return (
      <div className="min-h-screen bg-background p-6">
        <div className="mx-auto max-w-3xl">
          <button
            type="button"
            onClick={() => navigate("/assets")}
            className="mb-4 text-sm text-[#665c54] hover:text-[#3c3836]"
          >
            ← Activos
          </button>
          <div className="rounded-lg border border-[#cc241d]/20 bg-[#f2e5bc] p-6 text-center">
            <p className="mb-3 text-sm text-[#cc241d]">
              No se pudo cargar el activo.
            </p>
            <button
              type="button"
              onClick={() => refetchAsset()}
              className="rounded-md bg-[#458588] px-4 py-2 text-sm font-medium text-white hover:bg-[#458588]/90"
            >
              Reintentar
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // View mode
  // ---------------------------------------------------------------------------

  if (mode === "view") {
    return (
      <div className="min-h-screen bg-background p-6">
        <div className="mx-auto max-w-3xl">
          {/* Back button */}
          <button
            type="button"
            onClick={() => navigate("/assets")}
            className="mb-4 text-sm text-[#665c54] hover:text-[#3c3836]"
          >
            ← Activos
          </button>

          {/* Page header */}
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-[#3c3836]">
                {asset.code}
              </h1>
              <p className="mt-0.5 text-sm text-[#665c54]">{asset.description}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={handleEnterEdit}
                className="rounded-md bg-[#458588] px-4 py-2 text-sm font-medium text-white hover:bg-[#458588]/90"
              >
                Editar
              </button>
              {asset.status === "active" && !isRetiring && (
                <button
                  type="button"
                  onClick={handleEnterRetire}
                  className="rounded-md border border-[#cc241d]/30 bg-[#cc241d]/10 px-4 py-2 text-sm font-medium text-[#cc241d] hover:bg-[#cc241d]/20"
                >
                  Dar de Baja
                </button>
              )}
              {asset.status !== "retired" && !isRetiring && !showDeleteConfirm && (
                <button
                  type="button"
                  onClick={handleDeleteClick}
                  className="rounded-md border border-[#928374]/30 bg-[#928374]/10 px-4 py-2 text-sm font-medium text-[#928374] hover:bg-[#928374]/20"
                >
                  Eliminar
                </button>
              )}
            </div>
          </div>

          {/* Inline delete confirmation */}
          {showDeleteConfirm && (
            <div className="mb-4 rounded-lg border border-[#928374]/30 bg-[#f2e5bc] p-4">
              <p className="mb-3 text-sm text-[#3c3836]">
                ¿Confirmas eliminar este activo? Esta acción no se puede deshacer.
              </p>
              {deleteError && (
                <p className="mb-3 text-sm text-[#cc241d]" role="alert">
                  {deleteError}
                </p>
              )}
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={handleDeleteConfirm}
                  disabled={isDeletePending}
                  className="rounded-md bg-[#928374] px-4 py-2 text-sm font-medium text-white hover:bg-[#928374]/90 disabled:opacity-50"
                >
                  {isDeletePending ? "Eliminando..." : "Sí, eliminar"}
                </button>
                <button
                  type="button"
                  onClick={handleDeleteCancel}
                  disabled={isDeletePending}
                  className="rounded-md border border-[#bdae93] bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}
          {!showDeleteConfirm && deleteError && (
            <p className="mb-4 text-sm text-[#cc241d]" role="alert">
              {deleteError}
            </p>
          )}

          {/* Profile sections */}
          <div className="mb-6 rounded-lg border border-border bg-[#f2e5bc] p-6">
            <h2 className="mb-3 text-base font-semibold text-[#3c3836]">Identificación</h2>
            <dl className="divide-y divide-[#d5c4a1]">
              <FieldRow label="Código" value={<span className="font-medium">{asset.code}</span>} />
              <FieldRow label="Descripción" value={asset.description} />
              <FieldRow label="Categoría" value={asset.category} />
            </dl>
          </div>

          <div className="mb-6 rounded-lg border border-border bg-[#f2e5bc] p-6">
            <h2 className="mb-3 text-base font-semibold text-[#3c3836]">Valorización</h2>
            <dl className="divide-y divide-[#d5c4a1]">
              <FieldRow
                label="Costo Histórico"
                value={
                  <span className="font-mono text-right">{asset.historical_cost}</span>
                }
              />
              <FieldRow
                label="Valor Residual"
                value={
                  <span className="font-mono text-right">{asset.salvage_value}</span>
                }
              />
              <FieldRow
                label="Vida Útil"
                value={`${asset.useful_life_months} meses`}
              />
              <FieldRow
                label="Fecha de Adquisición"
                value={formatDate(asset.acquisition_date)}
              />
              <FieldRow
                label="Método de Depreciación"
                value={METHOD_LABELS[asset.depreciation_method] ?? asset.depreciation_method}
              />
            </dl>
          </div>

          <div className="mb-8 rounded-lg border border-border bg-[#f2e5bc] p-6">
            <h2 className="mb-3 text-base font-semibold text-[#3c3836]">Estado</h2>
            <dl className="divide-y divide-[#d5c4a1]">
              <FieldRow label="Estado actual" value={<StatusBadge status={asset.status} />} />
              {asset.retirement_date && (
                <FieldRow
                  label="Fecha de baja"
                  value={formatDate(asset.retirement_date)}
                />
              )}
              <FieldRow label="Registrado el" value={formatDateTime(asset.created_at)} />
              <FieldRow label="Última modificación" value={formatDateTime(asset.updated_at)} />
            </dl>
          </div>

          {/* Retire form — shown inline when isRetiring */}
          {isRetiring && (
            <div className="mb-8 rounded-lg border border-[#cc241d]/30 bg-[#fff3f3] p-6">
              <h2 className="mb-2 text-base font-semibold text-[#cc241d]">Dar de Baja al Activo</h2>
              <p className="mb-4 text-sm text-[#665c54]">
                Esta acción es irreversible. El activo quedará retirado permanentemente.
              </p>
              <div className="mb-4">
                <label
                  htmlFor="retire-date"
                  className="block text-sm font-medium text-[#665c54]"
                >
                  Fecha de Baja <span className="text-[#cc241d]">*</span>
                </label>
                <input
                  id="retire-date"
                  type="date"
                  value={retireDate}
                  onChange={(e) => setRetireDate(e.target.value)}
                  className="mt-1 rounded-md border border-[#bdae93] bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-[#cc241d]"
                />
              </div>
              {retireError && (
                <p className="mb-3 text-sm text-[#cc241d]" role="alert">
                  {retireError}
                </p>
              )}
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={handleRetireSubmit}
                  disabled={isRetirePending}
                  className="rounded-md bg-[#cc241d] px-5 py-2 text-sm font-medium text-white hover:bg-[#cc241d]/90 disabled:opacity-50"
                >
                  {isRetirePending ? "Procesando..." : "Confirmar Baja"}
                </button>
                <button
                  type="button"
                  onClick={handleCancelRetire}
                  className="rounded-md border border-[#bdae93] bg-background px-5 py-2 text-sm font-medium text-foreground hover:bg-accent"
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}

          {/* Audit history */}
          <div className="rounded-lg border border-border bg-[#f2e5bc]">
            <div className="border-b border-[#d5c4a1] px-6 py-4">
              <h2 className="text-base font-semibold text-[#3c3836]">Historial de Cambios</h2>
            </div>

            {auditLoading ? (
              <AuditSkeleton />
            ) : !auditLog || auditLog.length === 0 ? (
              <div className="px-6 py-8 text-center">
                <p className="text-sm text-[#7c6f64]">
                  Aún no hay cambios registrados para este activo.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-[#ebdbb2]">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium text-[#665c54]">
                        Fecha y hora
                      </th>
                      <th className="px-4 py-3 text-left font-medium text-[#665c54]">
                        Acción
                      </th>
                      <th className="px-4 py-3 text-left font-medium text-[#665c54]">
                        Campo
                      </th>
                      <th className="px-4 py-3 text-left font-medium text-[#665c54]">
                        Valor anterior
                      </th>
                      <th className="px-4 py-3 text-left font-medium text-[#665c54]">
                        Valor nuevo
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#d5c4a1]">
                    {auditLog.map((entry: AuditLogEntry) => (
                      <tr key={entry.log_id} className="hover:bg-[#ebdbb2]/50">
                        <td className="px-4 py-3 text-[#3c3836]">
                          {formatDateTime(entry.timestamp)}
                        </td>
                        <td className="px-4 py-3 text-[#3c3836]">
                          {ACTION_LABELS[entry.action] ?? entry.action}
                        </td>
                        <td className="px-4 py-3 text-[#3c3836]">
                          {entry.field ?? "—"}
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-[#665c54]">
                          {entry.old_value ?? "—"}
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-[#665c54]">
                          {entry.new_value ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Edit mode
  // ---------------------------------------------------------------------------

  if (!editValues) return null;

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-2xl">
        {/* Header */}
        <div className="mb-6 flex items-center gap-4">
          <button
            type="button"
            onClick={handleCancelEdit}
            className="text-sm text-[#665c54] hover:text-[#3c3836]"
          >
            ← Volver
          </button>
          <h1 className="text-2xl font-bold text-[#3c3836]">Editar Activo</h1>
        </div>

        <form onSubmit={handleEditSubmit} noValidate>
          {/* Section 1: Identificación */}
          <div className="mb-6 rounded-lg border border-border bg-[#f2e5bc] p-6">
            <h2 className="mb-4 text-lg font-semibold text-[#3c3836]">Identificación</h2>
            <div className="space-y-4">
              {/* Code */}
              <div>
                <label htmlFor="code" className="block text-sm font-medium text-[#665c54]">
                  Código <span className="text-[#cc241d]">*</span>
                </label>
                <input
                  id="code"
                  type="text"
                  value={editValues.code}
                  onChange={(e) => handleEditChange("code", e.target.value)}
                  onBlur={() => handleEditBlur("code")}
                  className={fieldClass("code")}
                  autoFocus
                />
                {showError("code")}
              </div>

              {/* Description */}
              <div>
                <label htmlFor="description" className="block text-sm font-medium text-[#665c54]">
                  Descripción <span className="text-[#cc241d]">*</span>
                </label>
                <input
                  id="description"
                  type="text"
                  value={editValues.description}
                  onChange={(e) => handleEditChange("description", e.target.value)}
                  onBlur={() => handleEditBlur("description")}
                  className={fieldClass("description")}
                />
                {showError("description")}
              </div>

              {/* Category */}
              <div>
                <label htmlFor="category" className="block text-sm font-medium text-[#665c54]">
                  Categoría <span className="text-[#cc241d]">*</span>
                </label>
                <input
                  id="category"
                  type="text"
                  value={editValues.category}
                  onChange={(e) => handleEditChange("category", e.target.value)}
                  onBlur={() => handleEditBlur("category")}
                  className={fieldClass("category")}
                />
                {showError("category")}
              </div>
            </div>
          </div>

          {/* Section 2: Valorización */}
          <div className="mb-6 rounded-lg border border-border bg-[#f2e5bc] p-6">
            <h2 className="mb-4 text-lg font-semibold text-[#3c3836]">Valorización</h2>
            <div className="space-y-4">
              {/* Historical cost */}
              <div>
                <label
                  htmlFor="historical_cost"
                  className="block text-sm font-medium text-[#665c54]"
                >
                  Costo Histórico <span className="text-[#cc241d]">*</span>
                </label>
                <input
                  id="historical_cost"
                  type="text"
                  inputMode="decimal"
                  value={editValues.historical_cost}
                  onChange={(e) => handleEditChange("historical_cost", e.target.value)}
                  onBlur={() => handleEditBlur("historical_cost")}
                  className={`${fieldClass("historical_cost")} font-mono text-right`}
                />
                {showError("historical_cost")}
              </div>

              {/* Salvage value */}
              <div>
                <label
                  htmlFor="salvage_value"
                  className="block text-sm font-medium text-[#665c54]"
                >
                  Valor Residual <span className="text-[#cc241d]">*</span>
                </label>
                <input
                  id="salvage_value"
                  type="text"
                  inputMode="decimal"
                  value={editValues.salvage_value}
                  onChange={(e) => handleEditChange("salvage_value", e.target.value)}
                  onBlur={() => handleEditBlur("salvage_value")}
                  className={`${fieldClass("salvage_value")} font-mono text-right`}
                />
                {showError("salvage_value")}
              </div>

              {/* Useful life months */}
              <div>
                <label
                  htmlFor="useful_life_months"
                  className="block text-sm font-medium text-[#665c54]"
                >
                  Vida Útil (meses) <span className="text-[#cc241d]">*</span>
                </label>
                <input
                  id="useful_life_months"
                  type="number"
                  min="1"
                  step="1"
                  value={editValues.useful_life_months}
                  onChange={(e) => handleEditChange("useful_life_months", e.target.value)}
                  onBlur={() => handleEditBlur("useful_life_months")}
                  className={fieldClass("useful_life_months")}
                />
                {showError("useful_life_months")}
              </div>

              {/* Acquisition date */}
              <div>
                <label
                  htmlFor="acquisition_date"
                  className="block text-sm font-medium text-[#665c54]"
                >
                  Fecha de Adquisición <span className="text-[#cc241d]">*</span>
                </label>
                <input
                  id="acquisition_date"
                  type="date"
                  value={editValues.acquisition_date}
                  onChange={(e) => handleEditChange("acquisition_date", e.target.value)}
                  onBlur={() => handleEditBlur("acquisition_date")}
                  className={fieldClass("acquisition_date")}
                />
                {showError("acquisition_date")}
              </div>

              {/* Depreciation method */}
              <div>
                <label
                  htmlFor="depreciation_method"
                  className="block text-sm font-medium text-[#665c54]"
                >
                  Método de Depreciación <span className="text-[#cc241d]">*</span>
                </label>
                <select
                  id="depreciation_method"
                  value={editValues.depreciation_method}
                  onChange={(e) =>
                    handleEditChange(
                      "depreciation_method",
                      e.target.value as DepreciationMethod
                    )
                  }
                  onBlur={() => handleEditBlur("depreciation_method")}
                  className={fieldClass("depreciation_method")}
                >
                  {DEPRECIATION_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                {showError("depreciation_method")}
              </div>
            </div>
          </div>

          {/* Submit error */}
          {editErrors.submit && (
            <p className="mb-4 text-sm text-[#cc241d]" role="alert">
              {editErrors.submit}
            </p>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={handleCancelEdit}
              className="rounded-md border border-[#bdae93] bg-background px-6 py-2 text-sm font-medium text-foreground hover:bg-accent"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isUpdating}
              className="rounded-md bg-[#458588] px-6 py-2 text-sm font-medium text-white hover:bg-[#458588]/90 disabled:opacity-50"
            >
              {isUpdating ? "Guardando..." : "Guardar Cambios"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
