/**
 * AssetForm — registration form for new fixed assets (Story 2.1).
 *
 * Two-section layout:
 *   Section 1 "Identificación": code, description, category
 *   Section 2 "Valorización": historical_cost, salvage_value,
 *             useful_life_months, acquisition_date, depreciation_method
 *
 * Validation fires onBlur (not while typing), errors are shown inline.
 * Data is NEVER lost on validation failure (AC2).
 * On success, navigates to /assets/:id (AC3).
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { useCreateAsset } from "../../hooks/useAssets";
import type { CreateAssetPayload, DepreciationMethod } from "../../types/asset";
import AppLayout from "@/components/layout/AppLayout";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FormValues {
  code: string;
  description: string;
  category: string;
  historical_cost: string;
  salvage_value: string;
  useful_life_months: string;
  acquisition_date: string;
  depreciation_method: DepreciationMethod;
}

interface FormErrors {
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

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function validateField(
  field: keyof FormValues,
  values: FormValues,
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
      if (isNaN(n) || strVal === "")
        return "El costo histórico debe ser un número válido";
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
      // Validate ISO 8601 date: YYYY-MM-DD
      const iso = /^\d{4}-\d{2}-\d{2}$/.test(strVal);
      if (!iso) return "Formato de fecha inválido (use DD/MM/AAAA)";
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

function validateAll(values: FormValues): FormErrors {
  const errors: FormErrors = {};
  const fields: (keyof FormValues)[] = [
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
    const err = validateField(field, values);
    if (err) errors[field] = err;
  }
  return errors;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DEPRECIATION_OPTIONS: { value: DepreciationMethod; label: string }[] = [
  { value: "straight_line", label: "Lineal" },
  { value: "sum_of_digits", label: "Suma de Dígitos" },
  { value: "declining_balance", label: "Saldo Decreciente" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AssetForm() {
  const navigate = useNavigate();
  const { mutate: createAsset, isPending } = useCreateAsset();

  const [values, setValues] = useState<FormValues>({
    code: "",
    description: "",
    category: "",
    historical_cost: "",
    salvage_value: "",
    useful_life_months: "",
    acquisition_date: "",
    depreciation_method: "straight_line",
  });

  const [errors, setErrors] = useState<FormErrors>({});
  const [touched, setTouched] = useState<
    Partial<Record<keyof FormValues, boolean>>
  >({});

  // -------------------------------------------------------------------------
  // Event handlers
  // -------------------------------------------------------------------------

  function handleChange(field: keyof FormValues, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
    // Clear error for field as soon as user starts editing again
    if (errors[field]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  }

  function handleBlur(field: keyof FormValues) {
    setTouched((prev) => ({ ...prev, [field]: true }));
    const err = validateField(field, values);
    setErrors((prev) => ({ ...prev, [field]: err }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    // Mark all fields as touched
    const allTouched = Object.fromEntries(
      Object.keys(values).map((k) => [k, true]),
    ) as Record<keyof FormValues, boolean>;
    setTouched(allTouched);

    const allErrors = validateAll(values);
    if (Object.keys(allErrors).length > 0) {
      setErrors(allErrors);
      // Focus the first invalid field
      const firstField = Object.keys(allErrors)[0] as keyof FormValues;
      const el = document.getElementById(firstField);
      el?.focus();
      return;
    }

    setErrors({});

    const payload: CreateAssetPayload = {
      code: values.code.trim(),
      description: values.description.trim(),
      category: values.category.trim(),
      historical_cost: values.historical_cost.trim(),
      salvage_value: values.salvage_value.trim(),
      useful_life_months: parseInt(values.useful_life_months, 10),
      acquisition_date: values.acquisition_date,
      depreciation_method: values.depreciation_method,
    };

    createAsset(payload, {
      onSuccess: (result) => {
        navigate(`/assets/${result.data.asset_id}`);
      },
      onError: (err) => {
        const message =
          err instanceof Error ? err.message : "Error al registrar el activo";
        if (err instanceof ApiError && err.field && err.field in values) {
          const field = err.field as keyof FormValues;
          setErrors((prev) => ({ ...prev, [field]: message }));
          setTouched((prev) => ({ ...prev, [field]: true }));
          document.getElementById(field)?.focus();
        } else {
          setErrors({ submit: message });
        }
      },
    });
  }

  function handleEscape() {
    const isDirty = Object.values(values).some(
      (v) => String(v).trim() !== "" && v !== "straight_line",
    );
    if (isDirty) {
      if (
        !window.confirm("¿Descartar cambios? Los datos ingresados se perderán.")
      )
        return;
    }
    navigate(-1);
  }

  // -------------------------------------------------------------------------
  // Field helpers
  // -------------------------------------------------------------------------

  function fieldClass(field: keyof FormValues): string {
    const base =
      "mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring";
    return errors[field] && touched[field]
      ? `${base} border-[#cc241d]`
      : `${base} border-[#bdae93]`;
  }

  function showError(field: keyof FormValues) {
    return touched[field] && errors[field] ? (
      <p className="mt-1 text-xs text-[#cc241d]" role="alert">
        {errors[field]}
      </p>
    ) : null;
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <AppLayout>
      <div className="min-h-screen bg-background p-6">
        <div className="mx-auto max-w-2xl">
          {/* Header */}
          <div className="mb-6 flex items-center gap-4">
            <button
              type="button"
              onClick={handleEscape}
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              ← Volver
            </button>
            <h1 className="text-2xl font-bold text-foreground">Nuevo Activo</h1>
          </div>

          <form onSubmit={handleSubmit} noValidate>
            {/* ----------------------------------------------------------------
               Section 1: Identificación
          ---------------------------------------------------------------- */}
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
                    value={values.code}
                    onChange={(e) => handleChange("code", e.target.value)}
                    onBlur={() => handleBlur("code")}
                    className={fieldClass("code")}
                    placeholder="LAP-001"
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
                    value={values.description}
                    onChange={(e) =>
                      handleChange("description", e.target.value)
                    }
                    onBlur={() => handleBlur("description")}
                    className={fieldClass("description")}
                    placeholder="HP Laptop 14 pulgadas"
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
                    value={values.category}
                    onChange={(e) => handleChange("category", e.target.value)}
                    onBlur={() => handleBlur("category")}
                    className={fieldClass("category")}
                    placeholder="Equipos de Cómputo"
                  />
                  {showError("category")}
                </div>
              </div>
            </div>

            {/* ----------------------------------------------------------------
               Section 2: Valorización
          ---------------------------------------------------------------- */}
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
                    value={values.historical_cost}
                    onChange={(e) =>
                      handleChange("historical_cost", e.target.value)
                    }
                    onBlur={() => handleBlur("historical_cost")}
                    className={`${fieldClass("historical_cost")} font-mono text-right`}
                    placeholder="1200.00"
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
                    value={values.salvage_value}
                    onChange={(e) =>
                      handleChange("salvage_value", e.target.value)
                    }
                    onBlur={() => handleBlur("salvage_value")}
                    className={`${fieldClass("salvage_value")} font-mono text-right`}
                    placeholder="120.00"
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
                    value={values.useful_life_months}
                    onChange={(e) =>
                      handleChange("useful_life_months", e.target.value)
                    }
                    onBlur={() => handleBlur("useful_life_months")}
                    className={fieldClass("useful_life_months")}
                    placeholder="60"
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
                    value={values.acquisition_date}
                    onChange={(e) =>
                      handleChange("acquisition_date", e.target.value)
                    }
                    onBlur={() => handleBlur("acquisition_date")}
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
                    value={values.depreciation_method}
                    onChange={(e) =>
                      handleChange(
                        "depreciation_method",
                        e.target.value as DepreciationMethod,
                      )
                    }
                    onBlur={() => handleBlur("depreciation_method")}
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
            {errors.submit && (
              <p className="mb-4 text-sm text-[#cc241d]" role="alert">
                {errors.submit}
              </p>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={handleEscape}
                className="rounded-md border border-[#bdae93] bg-background px-6 py-2 text-sm font-medium text-foreground hover:bg-accent"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={isPending}
                className="rounded-md bg-[#458588] px-6 py-2 text-sm font-medium text-white hover:bg-[#458588]/90 disabled:opacity-50"
              >
                {isPending ? "Guardando..." : "Registrar Activo"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </AppLayout>
  );
}
