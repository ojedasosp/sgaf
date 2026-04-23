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
import {
  useDeleteAsset,
  useGetAsset,
  useRetireAsset,
  useUpdateAsset,
} from "../../hooks/useAssets";
import AssetDepreciationSchedule from "../depreciation/AssetDepreciationSchedule";
import {
  useCreateMaintenanceEvent,
  useGetMaintenanceEvents,
} from "../../hooks/useMaintenance";
import MaintenanceHistory from "../maintenance/MaintenanceHistory";
import AppLayout from "@/components/layout/AppLayout";
import {
  useDeleteAssetPhoto,
  useGetAssetPhotos,
  useSetAssetPhotoPrimary,
  useUploadAssetPhoto,
} from "../../hooks/usePhotos";
import { openFilePicker, toWebviewUrl } from "../../lib/tauri";
import type {
  AuditLogEntry,
  Asset,
  AssetPhoto,
  AssetStatus,
  DepreciationMethod,
  RetireAssetPayload,
  UpdateAssetPayload,
} from "../../types/asset";
import type {
  CreateMaintenancePayload,
  MaintenanceEventType,
} from "../../types/maintenance";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<AssetStatus, { label: string; className: string }> =
  {
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
  none: "Sin Depreciación (Terrenos)",
};

const DEPRECIATION_OPTIONS: { value: DepreciationMethod; label: string }[] = [
  { value: "straight_line", label: "Lineal" },
  { value: "sum_of_digits", label: "Suma de Dígitos" },
  { value: "declining_balance", label: "Saldo Decreciente" },
  { value: "none", label: "Sin Depreciación (Terrenos)" },
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
      <dt className="w-full text-sm font-medium text-[#665c54] sm:w-44 sm:shrink-0">
        {label}
      </dt>
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
  // Import fields (Story 8.5) — empty string represents null/unset
  imported_accumulated_depreciation: string;
  additions_improvements: string;
  accounting_code: string;
  cost_center: string;
  supplier: string;
  invoice_number: string;
  location: string;
  characteristics: string;
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
  // Import field errors (Story 8.5)
  imported_accumulated_depreciation?: string;
  additions_improvements?: string;
  accounting_code?: string;
  cost_center?: string;
  supplier?: string;
  invoice_number?: string;
  location?: string;
  characteristics?: string;
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
    // import fields: null → empty string
    imported_accumulated_depreciation:
      asset.imported_accumulated_depreciation ?? "",
    additions_improvements: asset.additions_improvements ?? "",
    accounting_code: asset.accounting_code ?? "",
    cost_center: asset.cost_center ?? "",
    supplier: asset.supplier ?? "",
    invoice_number: asset.invoice_number ?? "",
    location: asset.location ?? "",
    characteristics: asset.characteristics ?? "",
  };
}

function validateEditField(
  field: keyof EditFormValues,
  values: EditFormValues,
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
      if (months < 0) return "La vida útil no puede ser negativa";
      // Allow 0 only for TERRENOS (method="none")
      if (months === 0 && values.depreciation_method !== "none")
        return "La vida útil debe ser mayor a 0 para este método de depreciación";
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
    case "imported_accumulated_depreciation": {
      if (strVal === "") break; // optional field
      const n = Number(strVal);
      if (isNaN(n)) return "Debe ser un número válido";
      if (n < 0) return "No puede ser negativo";
      // Cross-field: ≤ historical_cost + additions_improvements
      const hc = Number(String(values.historical_cost).trim());
      const ai = Number(String(values.additions_improvements).trim() || "0");
      if (!isNaN(hc) && hc > 0 && n > hc + ai) {
        return "La depreciación acumulada importada no puede superar el costo efectivo (costo histórico + adiciones)";
      }
      break;
    }
    case "additions_improvements": {
      if (strVal === "") break; // optional field
      const n2 = Number(strVal);
      if (isNaN(n2)) return "Debe ser un número válido";
      if (n2 < 0) return "No puede ser negativo";
      break;
    }
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
    "imported_accumulated_depreciation",
    "additions_improvements",
  ];
  for (const field of fields) {
    const err = validateEditField(field, values);
    if (err) errors[field] = err;
  }
  return errors;
}

// ---------------------------------------------------------------------------
// Maintenance form types and helpers
// ---------------------------------------------------------------------------

interface MaintenanceFormValues {
  entry_date: string;
  event_type: MaintenanceEventType | "";
  description: string;
  vendor: string;
  estimated_delivery_date: string;
  actual_delivery_date: string;
  actual_cost: string;
  received_by: string;
  closing_observation: string;
}

interface MaintenanceFormErrors {
  entry_date?: string;
  actual_delivery_date?: string;
  actual_cost?: string;
  submit?: string;
}

function validateMaintenanceForm(
  values: MaintenanceFormValues,
): MaintenanceFormErrors {
  const errors: MaintenanceFormErrors = {};
  if (!values.entry_date.trim()) {
    errors.entry_date = "La fecha de ingreso es obligatoria";
  } else {
    const today = new Date().toISOString().slice(0, 10);
    if (values.entry_date > today) {
      errors.entry_date = "La fecha de ingreso no puede ser futura";
    }
  }
  if (values.actual_cost.trim()) {
    const n = Number(values.actual_cost.trim());
    if (isNaN(n) || n < 0) {
      errors.actual_cost =
        "El costo real debe ser un número válido mayor o igual a 0";
    }
  }
  if (
    values.actual_delivery_date &&
    values.entry_date &&
    !errors.entry_date &&
    values.actual_delivery_date < values.entry_date
  ) {
    errors.actual_delivery_date =
      "La fecha de entrega real no puede ser anterior a la fecha de ingreso";
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

  const { data: auditLog, isLoading: auditLoading } =
    useGetAssetAuditLog(assetId);

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

  // Depreciation schedule section state
  const [isScheduleOpen, setIsScheduleOpen] = useState(false);

  // Import/accounting section state (view mode)
  const [isImportSectionOpen, setIsImportSectionOpen] = useState(false);

  // Photos section state
  const [isPhotosSectionOpen, setIsPhotosSectionOpen] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [pendingPhotoId, setPendingPhotoId] = useState<number | null>(null);
  const { data: assetPhotos, isLoading: photosLoading } = useGetAssetPhotos(assetId);
  const { mutate: uploadPhoto, isPending: isUploading } = useUploadAssetPhoto();
  const { mutate: deletePhoto } = useDeleteAssetPhoto();
  const { mutate: setPrimary } = useSetAssetPhotoPrimary();

  async function handleUploadPhoto() {
    const filePath = await openFilePicker({
      title: "Seleccionar foto del activo",
      filters: [{ name: "Imágenes", extensions: ["jpg", "jpeg", "png"] }],
    });
    if (!filePath) return;
    setPhotoError(null);
    uploadPhoto(
      { asset_id: assetId, file_path: filePath },
      {
        onError: (err) => {
          setPhotoError(err instanceof Error ? err.message : "Error al subir la foto");
        },
      },
    );
  }

  function handleDeletePhoto(photo: AssetPhoto) {
    if (!window.confirm("¿Eliminar esta foto?")) return;
    setPhotoError(null);
    setPendingPhotoId(photo.photo_id);
    deletePhoto(
      { photoId: photo.photo_id, assetId },
      {
        onSuccess: () => setPendingPhotoId(null),
        onError: (err) => {
          setPendingPhotoId(null);
          setPhotoError(err instanceof Error ? err.message : "Error al eliminar la foto");
        },
      },
    );
  }

  function handleSetPrimary(photo: AssetPhoto) {
    setPhotoError(null);
    setPendingPhotoId(photo.photo_id);
    setPrimary(
      { photoId: photo.photo_id, assetId },
      {
        onSuccess: () => setPendingPhotoId(null),
        onError: (err) => {
          setPendingPhotoId(null);
          setPhotoError(err instanceof Error ? err.message : "Error al cambiar la foto principal");
        },
      },
    );
  }

  // Maintenance form state
  const [isRegisteringMaintenance, setIsRegisteringMaintenance] =
    useState(false);
  const [maintenanceForm, setMaintenanceForm] =
    useState<MaintenanceFormValues>({
      entry_date: new Date().toISOString().slice(0, 10),
      event_type: "",
      description: "",
      vendor: "",
      estimated_delivery_date: "",
      actual_delivery_date: "",
      actual_cost: "",
      received_by: "",
      closing_observation: "",
    });
  const [maintenanceFormErrors, setMaintenanceFormErrors] =
    useState<MaintenanceFormErrors>({});

  const { data: maintenanceEvents, isLoading: maintenanceLoading } =
    useGetMaintenanceEvents(assetId);
  const { mutate: createEvent, isPending: isCreatingEvent } =
    useCreateMaintenanceEvent();

  // Retire mode state
  const [isRetiring, setIsRetiring] = useState(false);
  const [retireDate, setRetireDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
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
      (k) => editValues[k] !== original[k],
    );
    if (isDirty) {
      if (
        !window.confirm("¿Descartar cambios? Los datos ingresados se perderán.")
      )
        return;
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
      Object.keys(editValues).map((k) => [k, true]),
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

    // Impact warning — confirm before saving depreciation-affecting field changes (AC4)
    const HIGH_IMPACT_FIELDS: (keyof EditFormValues)[] = [
      "imported_accumulated_depreciation",
      "additions_improvements",
    ];
    const originalValues = asset ? assetToFormValues(asset) : null;
    if (originalValues) {
      const hasHighImpactChange = HIGH_IMPACT_FIELDS.some(
        (f) => editValues[f] !== originalValues[f],
      );
      if (hasHighImpactChange) {
        const confirmed = window.confirm(
          "Has modificado campos que afectan los cálculos de depreciación. ¿Deseas guardar los cambios?",
        );
        if (!confirmed) return;
      }
    }

    const payload: UpdateAssetPayload = {
      code: editValues.code.trim(),
      description: editValues.description.trim(),
      category: editValues.category.trim(),
      historical_cost: editValues.historical_cost.trim(),
      salvage_value: editValues.salvage_value.trim(),
      useful_life_months: parseInt(editValues.useful_life_months, 10),
      acquisition_date: editValues.acquisition_date,
      depreciation_method: editValues.depreciation_method,
      // import fields: empty string → null (stored as NULL in DB)
      imported_accumulated_depreciation:
        editValues.imported_accumulated_depreciation.trim() || null,
      additions_improvements:
        editValues.additions_improvements.trim() || null,
      accounting_code: editValues.accounting_code.trim() || null,
      cost_center: editValues.cost_center.trim() || null,
      supplier: editValues.supplier.trim() || null,
      invoice_number: editValues.invoice_number.trim() || null,
      location: editValues.location.trim() || null,
      characteristics: editValues.characteristics.trim() || null,
    };

    updateAsset(
      { id: assetId, payload },
      {
        onSuccess: () => {
          setMode("view");
        },
        onError: (err) => {
          const message =
            err instanceof Error ? err.message : "Error al guardar los cambios";
          if (
            err instanceof ApiError &&
            err.field &&
            editValues &&
            err.field in editValues
          ) {
            const field = err.field as keyof EditFormValues;
            setEditErrors((prev) => ({ ...prev, [field]: message }));
            setEditTouched((prev) => ({ ...prev, [field]: true }));
            document.getElementById(field)?.focus();
          } else {
            setEditErrors({ submit: message });
          }
        },
      },
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
            err instanceof ApiError
              ? err.message
              : "No se pudo dar de baja el activo.",
          );
        },
      },
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
          err instanceof ApiError
            ? err.message
            : "No se puede eliminar el activo.",
        );
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Maintenance form handlers
  // ---------------------------------------------------------------------------

  function handleRegisterMaintenance() {
    setMaintenanceForm({
      entry_date: new Date().toISOString().slice(0, 10),
      event_type: "",
      description: "",
      vendor: "",
      estimated_delivery_date: "",
      actual_delivery_date: "",
      actual_cost: "",
      received_by: "",
      closing_observation: "",
    });
    setMaintenanceFormErrors({});
    setIsRegisteringMaintenance(true);
  }

  function handleCancelRegisterMaintenance() {
    const today = new Date().toISOString().slice(0, 10);
    const isDirty =
      maintenanceForm.entry_date !== today ||
      maintenanceForm.description.trim() !== "" ||
      maintenanceForm.vendor.trim() !== "" ||
      maintenanceForm.event_type !== "" ||
      maintenanceForm.estimated_delivery_date !== "" ||
      maintenanceForm.actual_delivery_date !== "" ||
      maintenanceForm.actual_cost !== "" ||
      maintenanceForm.received_by !== "" ||
      maintenanceForm.closing_observation !== "";
    if (
      isDirty &&
      !window.confirm(
        "¿Descartar cambios? Los datos ingresados se perderán.",
      )
    )
      return;
    setIsRegisteringMaintenance(false);
  }

  function handleMaintenanceFormChange(
    field: keyof MaintenanceFormValues,
    value: string,
  ) {
    setMaintenanceForm((prev) => ({ ...prev, [field]: value }));
    if (field in maintenanceFormErrors) {
      setMaintenanceFormErrors((prev) => {
        const next = { ...prev };
        delete next[field as keyof MaintenanceFormErrors];
        return next;
      });
    }
  }

  function handleMaintenanceFormSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errors = validateMaintenanceForm(maintenanceForm);
    if (Object.keys(errors).length > 0) {
      setMaintenanceFormErrors(errors);
      return;
    }
    const payload: CreateMaintenancePayload = {
      asset_id: assetId,
      entry_date: maintenanceForm.entry_date,
      ...(maintenanceForm.event_type
        ? { event_type: maintenanceForm.event_type as MaintenanceEventType }
        : {}),
      ...(maintenanceForm.description.trim()
        ? { description: maintenanceForm.description.trim() }
        : {}),
      ...(maintenanceForm.vendor.trim()
        ? { vendor: maintenanceForm.vendor.trim() }
        : {}),
      ...(maintenanceForm.estimated_delivery_date
        ? { estimated_delivery_date: maintenanceForm.estimated_delivery_date }
        : {}),
      ...(maintenanceForm.actual_delivery_date
        ? { actual_delivery_date: maintenanceForm.actual_delivery_date }
        : {}),
      ...(maintenanceForm.actual_cost.trim()
        ? { actual_cost: maintenanceForm.actual_cost.trim() }
        : {}),
      ...(maintenanceForm.received_by.trim()
        ? { received_by: maintenanceForm.received_by.trim() }
        : {}),
      ...(maintenanceForm.closing_observation.trim()
        ? { closing_observation: maintenanceForm.closing_observation.trim() }
        : {}),
    };
    createEvent(payload, {
      onSuccess: () => {
        setIsRegisteringMaintenance(false);
      },
      onError: (err) => {
        setMaintenanceFormErrors({
          submit:
            err instanceof Error
              ? err.message
              : "Error al registrar el evento de mantenimiento",
        });
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
      <AppLayout>
        <div className="min-h-screen bg-background p-6">
          <div className="mx-auto max-w-3xl">
            <div className="mb-4 h-4 w-24 animate-pulse rounded bg-[#d5c4a1]" />
            <div className="mb-6 h-8 w-64 animate-pulse rounded bg-[#d5c4a1]" />
            <div className="rounded-lg border border-border bg-[#f2e5bc] p-6">
              <ProfileSkeleton />
            </div>
          </div>
        </div>
      </AppLayout>
    );
  }

  if (assetError || !asset) {
    return (
      <AppLayout>
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
      </AppLayout>
    );
  }

  // ---------------------------------------------------------------------------
  // View mode
  // ---------------------------------------------------------------------------

  if (mode === "view") {
    return (
      <AppLayout>
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
                <p className="mt-0.5 text-sm text-[#665c54]">
                  {asset.description}
                </p>
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
                {asset.status !== "retired" &&
                  !isRetiring &&
                  !showDeleteConfirm && (
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
                  ¿Confirmas eliminar este activo? Esta acción no se puede
                  deshacer.
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
              <h2 className="mb-3 text-base font-semibold text-[#3c3836]">
                Identificación
              </h2>
              <dl className="divide-y divide-[#d5c4a1]">
                <FieldRow
                  label="Código"
                  value={<span className="font-medium">{asset.code}</span>}
                />
                <FieldRow label="Descripción" value={asset.description} />
                <FieldRow label="Categoría" value={asset.category} />
              </dl>
            </div>

            <div className="mb-6 rounded-lg border border-border bg-[#f2e5bc] p-6">
              <h2 className="mb-3 text-base font-semibold text-[#3c3836]">
                Valorización
              </h2>
              <dl className="divide-y divide-[#d5c4a1]">
                <FieldRow
                  label="Costo Histórico"
                  value={
                    <span className="font-mono text-right">
                      {asset.historical_cost}
                    </span>
                  }
                />
                <FieldRow
                  label="Valor Residual"
                  value={
                    <span className="font-mono text-right">
                      {asset.salvage_value}
                    </span>
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
                  value={
                    METHOD_LABELS[asset.depreciation_method] ??
                    asset.depreciation_method
                  }
                />
              </dl>
            </div>

            <div className="mb-8 rounded-lg border border-border bg-[#f2e5bc] p-6">
              <h2 className="mb-3 text-base font-semibold text-[#3c3836]">
                Estado
              </h2>
              <dl className="divide-y divide-[#d5c4a1]">
                <FieldRow
                  label="Estado actual"
                  value={<StatusBadge status={asset.status} />}
                />
                {asset.retirement_date && (
                  <FieldRow
                    label="Fecha de baja"
                    value={formatDate(asset.retirement_date)}
                  />
                )}
                <FieldRow
                  label="Registrado el"
                  value={formatDateTime(asset.created_at)}
                />
                <FieldRow
                  label="Última modificación"
                  value={formatDateTime(asset.updated_at)}
                />
              </dl>
            </div>

            {/* Datos de Importación / Contables — collapsible (AC1) */}
            <div className="mb-6 rounded-lg border border-border bg-[#f2e5bc]">
              <button
                type="button"
                className="flex w-full items-center justify-between px-6 py-4 text-left"
                onClick={() => setIsImportSectionOpen((v) => !v)}
                aria-expanded={isImportSectionOpen}
              >
                <h2 className="text-base font-semibold text-[#3c3836]">
                  Datos de Importación / Contables
                </h2>
                <span className="text-sm text-[#665c54]">
                  {isImportSectionOpen ? "▲" : "▼"}
                </span>
              </button>
              {isImportSectionOpen && (
                <dl className="divide-y divide-[#d5c4a1] px-6 pb-4">
                  <FieldRow
                    label="Depreciación Acumulada al Importar"
                    value={
                      <span className="font-mono">
                        {asset.imported_accumulated_depreciation ?? "—"}
                      </span>
                    }
                  />
                  <FieldRow
                    label="Adiciones y Mejoras"
                    value={
                      <span className="font-mono">
                        {asset.additions_improvements ?? "—"}
                      </span>
                    }
                  />
                  <FieldRow
                    label="Código Contable (PUC)"
                    value={asset.accounting_code ?? "—"}
                  />
                  <FieldRow
                    label="Centro de Costo"
                    value={asset.cost_center ?? "—"}
                  />
                  <FieldRow
                    label="Proveedor"
                    value={asset.supplier ?? "—"}
                  />
                  <FieldRow
                    label="Factura"
                    value={asset.invoice_number ?? "—"}
                  />
                  <FieldRow
                    label="Ubicación"
                    value={asset.location ?? "—"}
                  />
                  <FieldRow
                    label="Características"
                    value={asset.characteristics ?? "—"}
                  />
                </dl>
              )}
            </div>

            {/* Fotos del Activo — collapsible */}
            <div className="mb-6 rounded-lg border border-border bg-[#f2e5bc]">
              <button
                type="button"
                className="flex w-full items-center justify-between px-6 py-4 text-left"
                onClick={() => setIsPhotosSectionOpen((v) => !v)}
                aria-expanded={isPhotosSectionOpen}
              >
                <h2 className="text-base font-semibold text-[#3c3836]">Fotos del Activo</h2>
                <span className="text-sm text-[#665c54]">{isPhotosSectionOpen ? "▲" : "▼"}</span>
              </button>
              {isPhotosSectionOpen && (
                <div className="px-6 pb-4">
                  <button
                    type="button"
                    onClick={handleUploadPhoto}
                    disabled={isUploading}
                    className="mb-4 rounded-md bg-[#458588] px-4 py-2 text-sm font-medium text-white hover:bg-[#458588]/90 disabled:opacity-50"
                  >
                    {isUploading ? "Subiendo..." : "Agregar Foto"}
                  </button>

                  {photoError && (
                    <p className="mb-3 text-xs text-[#9d0006]">{photoError}</p>
                  )}

                  {photosLoading ? (
                    <p className="text-sm text-[#928374]">Cargando fotos...</p>
                  ) : !assetPhotos || assetPhotos.length === 0 ? (
                    <p className="text-sm text-[#7c6f64]">No hay fotos registradas para este activo.</p>
                  ) : (
                    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                      {assetPhotos.map((photo) => {
                        const isThisPending = pendingPhotoId === photo.photo_id;
                        return (
                          <div
                            key={photo.photo_id}
                            className="relative rounded-lg border border-[#d5c4a1] bg-[#ebdbb2] p-2"
                          >
                            <img
                              src={toWebviewUrl(photo.file_path)}
                              alt="Foto del activo"
                              className="mb-2 h-32 w-full rounded object-cover"
                            />
                            {photo.is_primary === 1 && (
                              <span className="mb-1 inline-block rounded-full bg-[#98971a]/20 px-2 py-0.5 text-xs font-medium text-[#98971a]">
                                Principal
                              </span>
                            )}
                            <div className="flex flex-wrap gap-1">
                              {photo.is_primary !== 1 && (
                                <button
                                  type="button"
                                  onClick={() => handleSetPrimary(photo)}
                                  disabled={isThisPending}
                                  className="rounded bg-[#458588]/10 px-2 py-1 text-xs text-[#458588] hover:bg-[#458588]/20 disabled:opacity-50"
                                >
                                  Marcar principal
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => handleDeletePhoto(photo)}
                                disabled={isThisPending}
                                className="rounded bg-[#cc241d]/10 px-2 py-1 text-xs text-[#cc241d] hover:bg-[#cc241d]/20 disabled:opacity-50"
                              >
                                {isThisPending ? "..." : "Eliminar"}
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Retire form — shown inline when isRetiring */}
            {isRetiring && (
              <div className="mb-8 rounded-lg border border-[#cc241d]/30 bg-[#fff3f3] p-6">
                <h2 className="mb-2 text-base font-semibold text-[#cc241d]">
                  Dar de Baja al Activo
                </h2>
                <p className="mb-4 text-sm text-[#665c54]">
                  Esta acción es irreversible. El activo quedará retirado
                  permanentemente.
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
                <h2 className="text-base font-semibold text-[#3c3836]">
                  Historial de Cambios
                </h2>
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
                        <tr
                          key={entry.log_id}
                          className="hover:bg-[#ebdbb2]/50"
                        >
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

            {/* Depreciation schedule — collapsed by default, lazy-loaded on expand */}
            <div className="mt-6 rounded-lg border border-border bg-[#f2e5bc]">
              <div className="border-b border-[#d5c4a1] px-6 py-4">
                <button
                  type="button"
                  onClick={() => setIsScheduleOpen((prev) => !prev)}
                  className="flex w-full items-center justify-between text-base font-semibold text-[#3c3836] hover:text-[#504945]"
                >
                  Tabla de Depreciación
                  <span className="text-sm text-[#665c54]">
                    {isScheduleOpen ? "▲" : "▼"}
                  </span>
                </button>
              </div>
              {isScheduleOpen && (
                <AssetDepreciationSchedule assetId={assetId} />
              )}
            </div>

            {/* Maintenance section */}
            <div className="mt-6 rounded-lg border border-border bg-[#f2e5bc]">
              <div className="flex items-center justify-between border-b border-[#d5c4a1] px-6 py-4">
                <h2 className="text-base font-semibold text-[#3c3836]">
                  Historial de Mantenimiento
                </h2>
                {asset.status === "active" && !isRegisteringMaintenance && (
                  <button
                    type="button"
                    onClick={handleRegisterMaintenance}
                    className="rounded-md bg-[#458588] px-4 py-2 text-sm font-medium text-white hover:bg-[#458588]/90"
                  >
                    Registrar Mantenimiento
                  </button>
                )}
              </div>

              {/* Inline registration form */}
              {isRegisteringMaintenance && (
                <form
                  onSubmit={handleMaintenanceFormSubmit}
                  noValidate
                  className="border-b border-[#d5c4a1] px-6 py-4"
                >
                  <h3 className="mb-4 text-sm font-semibold text-[#3c3836]">
                    Nuevo evento de mantenimiento
                  </h3>
                  <div className="space-y-4">
                    {/* Entry date */}
                    <div>
                      <label
                        htmlFor="maint-entry-date"
                        className="block text-sm font-medium text-[#665c54]"
                      >
                        Fecha de Ingreso{" "}
                        <span className="text-[#cc241d]">*</span>
                      </label>
                      <input
                        id="maint-entry-date"
                        type="date"
                        value={maintenanceForm.entry_date}
                        onChange={(e) =>
                          handleMaintenanceFormChange(
                            "entry_date",
                            e.target.value,
                          )
                        }
                        className={`mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring ${maintenanceFormErrors.entry_date ? "border-[#cc241d]" : "border-[#bdae93]"}`}
                      />
                      {maintenanceFormErrors.entry_date && (
                        <p className="mt-1 text-xs text-[#cc241d]" role="alert">
                          {maintenanceFormErrors.entry_date}
                        </p>
                      )}
                    </div>

                    {/* Event type */}
                    <div>
                      <label
                        htmlFor="maint-event-type"
                        className="block text-sm font-medium text-[#665c54]"
                      >
                        Tipo de Mantenimiento
                      </label>
                      <select
                        id="maint-event-type"
                        value={maintenanceForm.event_type}
                        onChange={(e) =>
                          handleMaintenanceFormChange(
                            "event_type",
                            e.target.value,
                          )
                        }
                        className="mt-1 w-full rounded-md border border-[#bdae93] bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      >
                        <option value="">— Seleccionar —</option>
                        <option value="preventivo">Preventivo</option>
                        <option value="correctivo">Correctivo</option>
                        <option value="inspeccion">Inspección</option>
                      </select>
                    </div>

                    {/* Description */}
                    <div>
                      <label
                        htmlFor="maint-description"
                        className="block text-sm font-medium text-[#665c54]"
                      >
                        Descripción
                      </label>
                      <input
                        id="maint-description"
                        type="text"
                        value={maintenanceForm.description}
                        onChange={(e) =>
                          handleMaintenanceFormChange(
                            "description",
                            e.target.value,
                          )
                        }
                        className="mt-1 w-full rounded-md border border-[#bdae93] bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    </div>

                    {/* Vendor */}
                    <div>
                      <label
                        htmlFor="maint-vendor"
                        className="block text-sm font-medium text-[#665c54]"
                      >
                        Proveedor
                      </label>
                      <input
                        id="maint-vendor"
                        type="text"
                        value={maintenanceForm.vendor}
                        onChange={(e) =>
                          handleMaintenanceFormChange("vendor", e.target.value)
                        }
                        className="mt-1 w-full rounded-md border border-[#bdae93] bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    </div>

                    {/* Estimated delivery date */}
                    <div>
                      <label
                        htmlFor="maint-estimated-delivery"
                        className="block text-sm font-medium text-[#665c54]"
                      >
                        Fecha Est. de Entrega
                      </label>
                      <input
                        id="maint-estimated-delivery"
                        type="date"
                        value={maintenanceForm.estimated_delivery_date}
                        onChange={(e) =>
                          handleMaintenanceFormChange(
                            "estimated_delivery_date",
                            e.target.value,
                          )
                        }
                        className="mt-1 w-full rounded-md border border-[#bdae93] bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    </div>

                    {/* Actual delivery date */}
                    <div>
                      <label
                        htmlFor="maint-actual-delivery"
                        className="block text-sm font-medium text-[#665c54]"
                      >
                        Fecha Entrega Real
                      </label>
                      <input
                        id="maint-actual-delivery"
                        type="date"
                        value={maintenanceForm.actual_delivery_date}
                        onChange={(e) =>
                          handleMaintenanceFormChange(
                            "actual_delivery_date",
                            e.target.value,
                          )
                        }
                        className={`mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring ${maintenanceFormErrors.actual_delivery_date ? "border-[#cc241d]" : "border-[#bdae93]"}`}
                      />
                      {maintenanceFormErrors.actual_delivery_date && (
                        <p className="mt-1 text-xs text-[#cc241d]" role="alert">
                          {maintenanceFormErrors.actual_delivery_date}
                        </p>
                      )}
                    </div>

                    {/* Actual cost */}
                    <div>
                      <label
                        htmlFor="maint-actual-cost"
                        className="block text-sm font-medium text-[#665c54]"
                      >
                        Costo Real
                      </label>
                      <input
                        id="maint-actual-cost"
                        type="text"
                        inputMode="decimal"
                        value={maintenanceForm.actual_cost}
                        onChange={(e) =>
                          handleMaintenanceFormChange(
                            "actual_cost",
                            e.target.value,
                          )
                        }
                        className={`mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-ring ${maintenanceFormErrors.actual_cost ? "border-[#cc241d]" : "border-[#bdae93]"}`}
                      />
                      {maintenanceFormErrors.actual_cost && (
                        <p className="mt-1 text-xs text-[#cc241d]" role="alert">
                          {maintenanceFormErrors.actual_cost}
                        </p>
                      )}
                    </div>

                    {/* Received by */}
                    <div>
                      <label
                        htmlFor="maint-received-by"
                        className="block text-sm font-medium text-[#665c54]"
                      >
                        Recibido por
                      </label>
                      <input
                        id="maint-received-by"
                        type="text"
                        value={maintenanceForm.received_by}
                        onChange={(e) =>
                          handleMaintenanceFormChange(
                            "received_by",
                            e.target.value,
                          )
                        }
                        className="mt-1 w-full rounded-md border border-[#bdae93] bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    </div>

                    {/* Closing observation */}
                    <div>
                      <label
                        htmlFor="maint-closing-obs"
                        className="block text-sm font-medium text-[#665c54]"
                      >
                        Observación de cierre
                      </label>
                      <textarea
                        id="maint-closing-obs"
                        rows={3}
                        value={maintenanceForm.closing_observation}
                        onChange={(e) =>
                          handleMaintenanceFormChange(
                            "closing_observation",
                            e.target.value,
                          )
                        }
                        className="mt-1 w-full rounded-md border border-[#bdae93] bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    </div>
                  </div>

                  {maintenanceFormErrors.submit && (
                    <p className="mt-3 text-sm text-[#cc241d]" role="alert">
                      {maintenanceFormErrors.submit}
                    </p>
                  )}

                  <div className="mt-4 flex gap-3">
                    <button
                      type="submit"
                      disabled={isCreatingEvent}
                      className="rounded-md bg-[#458588] px-5 py-2 text-sm font-medium text-white hover:bg-[#458588]/90 disabled:opacity-50"
                    >
                      {isCreatingEvent ? "Guardando..." : "Guardar"}
                    </button>
                    <button
                      type="button"
                      onClick={handleCancelRegisterMaintenance}
                      disabled={isCreatingEvent}
                      className="rounded-md border border-[#bdae93] bg-background px-5 py-2 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50"
                    >
                      Cancelar
                    </button>
                  </div>
                </form>
              )}

              {/* Maintenance history table */}
              <div className="px-6 py-4">
                {maintenanceLoading ? (
                  <p className="text-sm text-[#928374]">Cargando historial...</p>
                ) : (
                  <MaintenanceHistory events={maintenanceEvents ?? []} />
                )}
              </div>
            </div>
          </div>
        </div>
      </AppLayout>
    );
  }

  // ---------------------------------------------------------------------------
  // Edit mode
  // ---------------------------------------------------------------------------

  if (!editValues) return null;

  return (
    <AppLayout>
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
              <h2 className="mb-4 text-lg font-semibold text-[#3c3836]">
                Identificación
              </h2>
              <div className="space-y-4">
                {/* Code */}
                <div>
                  <label
                    htmlFor="code"
                    className="block text-sm font-medium text-[#665c54]"
                  >
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
                  <label
                    htmlFor="description"
                    className="block text-sm font-medium text-[#665c54]"
                  >
                    Descripción <span className="text-[#cc241d]">*</span>
                  </label>
                  <input
                    id="description"
                    type="text"
                    value={editValues.description}
                    onChange={(e) =>
                      handleEditChange("description", e.target.value)
                    }
                    onBlur={() => handleEditBlur("description")}
                    className={fieldClass("description")}
                  />
                  {showError("description")}
                </div>

                {/* Category */}
                <div>
                  <label
                    htmlFor="category"
                    className="block text-sm font-medium text-[#665c54]"
                  >
                    Categoría <span className="text-[#cc241d]">*</span>
                  </label>
                  <input
                    id="category"
                    type="text"
                    value={editValues.category}
                    onChange={(e) =>
                      handleEditChange("category", e.target.value)
                    }
                    onBlur={() => handleEditBlur("category")}
                    className={fieldClass("category")}
                  />
                  {showError("category")}
                </div>
              </div>
            </div>

            {/* Section 2: Valorización */}
            <div className="mb-6 rounded-lg border border-border bg-[#f2e5bc] p-6">
              <h2 className="mb-4 text-lg font-semibold text-[#3c3836]">
                Valorización
              </h2>
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
                    onChange={(e) =>
                      handleEditChange("historical_cost", e.target.value)
                    }
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
                    onChange={(e) =>
                      handleEditChange("salvage_value", e.target.value)
                    }
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
                    min="0"
                    step="1"
                    value={editValues.useful_life_months}
                    onChange={(e) =>
                      handleEditChange("useful_life_months", e.target.value)
                    }
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
                    Fecha de Adquisición{" "}
                    <span className="text-[#cc241d]">*</span>
                  </label>
                  <input
                    id="acquisition_date"
                    type="date"
                    value={editValues.acquisition_date}
                    onChange={(e) =>
                      handleEditChange("acquisition_date", e.target.value)
                    }
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
                    Método de Depreciación{" "}
                    <span className="text-[#cc241d]">*</span>
                  </label>
                  <select
                    id="depreciation_method"
                    value={editValues.depreciation_method}
                    onChange={(e) =>
                      handleEditChange(
                        "depreciation_method",
                        e.target.value as DepreciationMethod,
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

            {/* Section 3: Datos de Importación / Contables (Story 8.5) */}
            <div className="mb-6 rounded-lg border border-border bg-[#f2e5bc] p-6">
              <h2 className="mb-4 text-lg font-semibold text-[#3c3836]">
                Datos de Importación / Contables
              </h2>
              <div className="space-y-4">
                {/* imported_accumulated_depreciation */}
                <div>
                  <label
                    htmlFor="imported_accumulated_depreciation"
                    className="block text-sm font-medium text-[#665c54]"
                  >
                    Depreciación Acumulada al Importar
                  </label>
                  <input
                    id="imported_accumulated_depreciation"
                    type="text"
                    inputMode="decimal"
                    value={editValues.imported_accumulated_depreciation}
                    onChange={(e) =>
                      handleEditChange(
                        "imported_accumulated_depreciation",
                        e.target.value,
                      )
                    }
                    onBlur={() =>
                      handleEditBlur("imported_accumulated_depreciation")
                    }
                    className={`${fieldClass("imported_accumulated_depreciation")} font-mono text-right`}
                    placeholder="0.00"
                  />
                  {/* AC3: warning always visible (intentionally improved over spec's focus-only) */}
                  <p className="mt-1 text-xs text-[#d79921]">
                    ⚠ Modificar este valor recalculará el valor en libros del activo
                  </p>
                  {showError("imported_accumulated_depreciation")}
                </div>

                {/* additions_improvements */}
                <div>
                  <label
                    htmlFor="additions_improvements"
                    className="block text-sm font-medium text-[#665c54]"
                  >
                    Adiciones y Mejoras Capitalizadas
                  </label>
                  <input
                    id="additions_improvements"
                    type="text"
                    inputMode="decimal"
                    value={editValues.additions_improvements}
                    onChange={(e) =>
                      handleEditChange("additions_improvements", e.target.value)
                    }
                    onBlur={() => handleEditBlur("additions_improvements")}
                    className={`${fieldClass("additions_improvements")} font-mono text-right`}
                    placeholder="0.00"
                  />
                  {/* AC3: warning always visible (intentionally improved over spec's focus-only) */}
                  <p className="mt-1 text-xs text-[#d79921]">
                    ⚠ Modificar afecta la base depreciable
                  </p>
                  {showError("additions_improvements")}
                </div>

                {/* accounting_code */}
                <div>
                  <label
                    htmlFor="accounting_code"
                    className="block text-sm font-medium text-[#665c54]"
                  >
                    Código Contable (PUC)
                  </label>
                  <input
                    id="accounting_code"
                    type="text"
                    value={editValues.accounting_code}
                    onChange={(e) =>
                      handleEditChange("accounting_code", e.target.value)
                    }
                    onBlur={() => handleEditBlur("accounting_code")}
                    className={fieldClass("accounting_code")}
                    placeholder="1524"
                  />
                </div>

                {/* cost_center */}
                <div>
                  <label
                    htmlFor="cost_center"
                    className="block text-sm font-medium text-[#665c54]"
                  >
                    Centro de Costo
                  </label>
                  <input
                    id="cost_center"
                    type="text"
                    value={editValues.cost_center}
                    onChange={(e) =>
                      handleEditChange("cost_center", e.target.value)
                    }
                    onBlur={() => handleEditBlur("cost_center")}
                    className={fieldClass("cost_center")}
                    placeholder="CC-01"
                  />
                </div>

                {/* supplier */}
                <div>
                  <label
                    htmlFor="supplier"
                    className="block text-sm font-medium text-[#665c54]"
                  >
                    Proveedor
                  </label>
                  <input
                    id="supplier"
                    type="text"
                    value={editValues.supplier}
                    onChange={(e) =>
                      handleEditChange("supplier", e.target.value)
                    }
                    onBlur={() => handleEditBlur("supplier")}
                    className={fieldClass("supplier")}
                    placeholder="Nombre del proveedor"
                  />
                </div>

                {/* invoice_number */}
                <div>
                  <label
                    htmlFor="invoice_number"
                    className="block text-sm font-medium text-[#665c54]"
                  >
                    Factura
                  </label>
                  <input
                    id="invoice_number"
                    type="text"
                    value={editValues.invoice_number}
                    onChange={(e) =>
                      handleEditChange("invoice_number", e.target.value)
                    }
                    onBlur={() => handleEditBlur("invoice_number")}
                    className={fieldClass("invoice_number")}
                    placeholder="FAC-2024-001"
                  />
                </div>

                {/* location */}
                <div>
                  <label
                    htmlFor="location"
                    className="block text-sm font-medium text-[#665c54]"
                  >
                    Ubicación
                  </label>
                  <input
                    id="location"
                    type="text"
                    value={editValues.location}
                    onChange={(e) =>
                      handleEditChange("location", e.target.value)
                    }
                    onBlur={() => handleEditBlur("location")}
                    className={fieldClass("location")}
                    placeholder="Oficina 201"
                  />
                </div>

                {/* characteristics */}
                <div>
                  <label
                    htmlFor="characteristics"
                    className="block text-sm font-medium text-[#665c54]"
                  >
                    Características
                  </label>
                  <input
                    id="characteristics"
                    type="text"
                    value={editValues.characteristics}
                    onChange={(e) =>
                      handleEditChange("characteristics", e.target.value)
                    }
                    onBlur={() => handleEditBlur("characteristics")}
                    className={fieldClass("characteristics")}
                    placeholder="Especificaciones técnicas"
                  />
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
    </AppLayout>
  );
}
