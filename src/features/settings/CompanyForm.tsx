import { useEffect, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { openFilePicker } from "../../lib/tauri";
import { useUpdateCompanyConfig } from "../../hooks/useConfig";
import { ApiError } from "../../lib/api";

interface Props {
  initialData: {
    company_name: string;
    company_nit: string;
    logo_path: string | null;
  };
}

interface FormErrors {
  company_name?: string;
  company_nit?: string;
  submit?: string;
}

export default function CompanyForm({ initialData }: Props) {
  const [companyName, setCompanyName] = useState(initialData.company_name);
  const [companyNit, setCompanyNit] = useState(initialData.company_nit);
  const [logoPath, setLogoPath] = useState<string | null>(
    initialData.logo_path,
  );
  const [errors, setErrors] = useState<FormErrors>({});
  const [success, setSuccess] = useState(false);

  const updateMutation = useUpdateCompanyConfig();

  useEffect(() => {
    if (!success) return;
    const timer = setTimeout(() => setSuccess(false), 4000);
    return () => clearTimeout(timer);
  }, [success]);

  function validate(): FormErrors {
    const errs: FormErrors = {};
    if (!companyName.trim()) {
      errs.company_name = "El nombre de empresa es obligatorio";
    }
    if (!companyNit.trim()) {
      errs.company_nit = "El NIT es obligatorio";
    } else if (!/^\d+$/.test(companyNit.trim())) {
      errs.company_nit = "El NIT debe contener solo números";
    }
    return errs;
  }

  async function handleLogoSelect() {
    const path = await openFilePicker({
      title: "Seleccionar logo de empresa",
      filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg"] }],
    });
    if (path) {
      setLogoPath(path);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSuccess(false);

    const errs = validate();
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
    setErrors({});

    updateMutation.mutate(
      {
        company_name: companyName.trim(),
        company_nit: companyNit.trim(),
        logo_path: logoPath,
      },
      {
        onSuccess: () => {
          setSuccess(true);
          setErrors({});
        },
        onError: (err) => {
          if (err instanceof ApiError && err.field) {
            setErrors({ [err.field]: err.message });
          } else {
            setErrors({
              submit:
                err instanceof Error
                  ? err.message
                  : "Error al guardar cambios.",
            });
          }
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <h2 className="text-base font-semibold text-[#d79921] mb-4">
        Información de Empresa
      </h2>

      <div className="space-y-4">
        {/* Company Name */}
        <div>
          <label
            htmlFor="company_name"
            className="mb-1 block text-sm font-medium text-[#3c3836]"
          >
            Razón Social <span className="text-[#cc241d]">*</span>
          </label>
          <input
            id="company_name"
            type="text"
            maxLength={100}
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            className="w-full rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-2 text-[#3c3836] focus:outline-none focus:ring-2 focus:ring-[#d79921]"
            placeholder="Mi Empresa S.A.S"
          />
          {errors.company_name && (
            <p className="mt-1 text-sm text-[#cc241d]">
              {errors.company_name}
            </p>
          )}
        </div>

        {/* NIT */}
        <div>
          <label
            htmlFor="company_nit"
            className="mb-1 block text-sm font-medium text-[#3c3836]"
          >
            NIT <span className="text-[#cc241d]">*</span>
          </label>
          <input
            id="company_nit"
            type="text"
            value={companyNit}
            onChange={(e) => setCompanyNit(e.target.value)}
            className="w-full rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-2 text-[#3c3836] focus:outline-none focus:ring-2 focus:ring-[#d79921]"
            placeholder="9001234560"
          />
          {errors.company_nit && (
            <p className="mt-1 text-sm text-[#cc241d]">{errors.company_nit}</p>
          )}
        </div>

        {/* Logo Upload */}
        <div>
          <label className="mb-1 block text-sm font-medium text-[#3c3836]">
            Logo de Empresa (opcional)
          </label>
          <button
            type="button"
            onClick={handleLogoSelect}
            className="rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-2 text-sm text-[#3c3836] hover:bg-[#f2e5bc]"
          >
            {logoPath ? "Cambiar logo" : "Seleccionar logo (PNG/JPG)"}
          </button>
          {logoPath && (
            <div className="mt-2">
              <img
                src={convertFileSrc(logoPath)}
                alt="Logo preview"
                className="max-h-16 max-w-[200px] rounded object-contain"
              />
            </div>
          )}
        </div>
      </div>

      {/* Submit error */}
      {errors.submit && (
        <p className="mt-4 text-sm text-[#cc241d]">{errors.submit}</p>
      )}

      {/* Success message */}
      {success && (
        <p className="mt-4 text-sm text-[#98971a]">
          Cambios guardados correctamente.
        </p>
      )}

      <div className="mt-6">
        <button
          type="submit"
          disabled={updateMutation.isPending}
          className="rounded-md bg-[#d79921] px-6 py-2 text-sm font-medium text-[#fbf1c7] hover:bg-[#b57614] disabled:opacity-50"
        >
          {updateMutation.isPending ? "Guardando..." : "Guardar cambios"}
        </button>
      </div>
    </form>
  );
}
