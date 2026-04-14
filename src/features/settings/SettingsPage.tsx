import { useEffect, useState } from "react";
import AppLayout from "../../components/layout/AppLayout";
import LoadingSpinner from "../../components/shared/LoadingSpinner";
import ErrorMessage from "../../components/shared/ErrorMessage";
import CompanyForm from "./CompanyForm";
import { useGetCompanyConfig, useChangePassword, useGetCategories, useUpdateCategories } from "../../hooks/useConfig";
import { ApiError } from "../../lib/api";

interface PasswordErrors {
  current_password?: string;
  new_password?: string;
  new_password_confirm?: string;
  submit?: string;
}

export default function SettingsPage() {
  const { data: companyConfig, isLoading, isError } = useGetCompanyConfig();

  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [pwErrors, setPwErrors] = useState<PasswordErrors>({});
  const [pwSuccess, setPwSuccess] = useState(false);

  const changePasswordMutation = useChangePassword();

  // Categories state
  const { data: categories = [], isLoading: catLoading } = useGetCategories();
  const updateCategoriesMutation = useUpdateCategories();
  const [newCategory, setNewCategory] = useState("");
  const [catError, setCatError] = useState<string | undefined>();
  const [catSuccess, setCatSuccess] = useState(false);

  useEffect(() => {
    if (!pwSuccess) return;
    const timer = setTimeout(() => setPwSuccess(false), 4000);
    return () => clearTimeout(timer);
  }, [pwSuccess]);

  useEffect(() => {
    if (!catSuccess) return;
    const timer = setTimeout(() => setCatSuccess(false), 4000);
    return () => clearTimeout(timer);
  }, [catSuccess]);

  function handleAddCategory() {
    const trimmed = newCategory.trim();
    if (!trimmed) {
      setCatError("El nombre de la categoría no puede estar vacío");
      return;
    }
    if (categories.includes(trimmed)) {
      setCatError("Esa categoría ya existe");
      return;
    }
    const updated = [...categories, trimmed];
    updateCategoriesMutation.mutate(updated, {
      onSuccess: () => {
        setNewCategory("");
        setCatError(undefined);
        setCatSuccess(true);
      },
      onError: () => setCatError("Error al guardar la categoría"),
    });
  }

  function handleRemoveCategory(index: number) {
    const updated = categories.filter((_, i) => i !== index);
    updateCategoriesMutation.mutate(updated, {
      onSuccess: () => {
        setCatError(undefined);
        setCatSuccess(true);
      },
      onError: () => setCatError("Error al eliminar la categoría"),
    });
  }

  function validatePassword(): PasswordErrors {
    const errs: PasswordErrors = {};
    if (!currentPassword) {
      errs.current_password = "La contraseña actual es obligatoria";
    }
    if (newPassword.length < 8) {
      errs.new_password = "La contraseña debe tener al menos 8 caracteres";
    }
    if (newPassword !== newPasswordConfirm) {
      errs.new_password_confirm = "Las contraseñas no coinciden";
    }
    return errs;
  }

  function handlePasswordSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPwSuccess(false);

    const errs = validatePassword();
    if (Object.keys(errs).length > 0) {
      setPwErrors(errs);
      return;
    }
    setPwErrors({});

    changePasswordMutation.mutate(
      {
        current_password: currentPassword,
        new_password: newPassword,
        new_password_confirm: newPasswordConfirm,
      },
      {
        onSuccess: () => {
          setPwSuccess(true);
          setPwErrors({});
          setCurrentPassword("");
          setNewPassword("");
          setNewPasswordConfirm("");
        },
        onError: (err) => {
          if (err instanceof ApiError && err.field) {
            setPwErrors({ [err.field]: err.message });
          } else {
            setPwErrors({
              submit:
                err instanceof Error
                  ? err.message
                  : "Error al cambiar contraseña.",
            });
          }
        },
      },
    );
  }

  return (
    <AppLayout>
    <div className= "m-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-[#3c3836]">Configuración</h1>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <ErrorMessage message="Error al cargar la configuración." />
      ) : companyConfig ? (
        <div className="max-w-lg">
          {/* Company Info Section */}
          <CompanyForm initialData={companyConfig} />

          {/* Password Change Section */}
          <div className="border-t border-[#d5c4a1] pt-6 mt-6">
            <h2 className="text-base font-semibold text-[#d79921] mb-4">
              Cambiar Contraseña
            </h2>

            <form onSubmit={handlePasswordSubmit}>
              <div className="space-y-4">
                {/* Current Password */}
                <div>
                  <label
                    htmlFor="current_password"
                    className="mb-1 block text-sm font-medium text-[#3c3836]"
                  >
                    Contraseña actual <span className="text-[#cc241d]">*</span>
                  </label>
                  <input
                    id="current_password"
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="w-full rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-2 text-[#3c3836] focus:outline-none focus:ring-2 focus:ring-[#d79921]"
                  />
                  {pwErrors.current_password && (
                    <p className="mt-1 text-sm text-[#cc241d]">
                      {pwErrors.current_password}
                    </p>
                  )}
                </div>

                {/* New Password */}
                <div>
                  <label
                    htmlFor="new_password"
                    className="mb-1 block text-sm font-medium text-[#3c3836]"
                  >
                    Nueva contraseña <span className="text-[#cc241d]">*</span>
                  </label>
                  <input
                    id="new_password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-2 text-[#3c3836] focus:outline-none focus:ring-2 focus:ring-[#d79921]"
                  />
                  <p className="mt-1 text-xs text-[#928374]">
                    Al menos 8 caracteres
                  </p>
                  {pwErrors.new_password && (
                    <p className="mt-1 text-sm text-[#cc241d]">
                      {pwErrors.new_password}
                    </p>
                  )}
                </div>

                {/* Confirm New Password */}
                <div>
                  <label
                    htmlFor="new_password_confirm"
                    className="mb-1 block text-sm font-medium text-[#3c3836]"
                  >
                    Confirmar nueva contraseña{" "}
                    <span className="text-[#cc241d]">*</span>
                  </label>
                  <input
                    id="new_password_confirm"
                    type="password"
                    value={newPasswordConfirm}
                    onChange={(e) => setNewPasswordConfirm(e.target.value)}
                    className="w-full rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-2 text-[#3c3836] focus:outline-none focus:ring-2 focus:ring-[#d79921]"
                  />
                  {pwErrors.new_password_confirm && (
                    <p className="mt-1 text-sm text-[#cc241d]">
                      {pwErrors.new_password_confirm}
                    </p>
                  )}
                </div>
              </div>

              {/* Submit error */}
              {pwErrors.submit && (
                <p className="mt-4 text-sm text-[#cc241d]">
                  {pwErrors.submit}
                </p>
              )}

              {/* Success message */}
              {pwSuccess && (
                <p className="mt-4 text-sm text-[#98971a]">
                  Contraseña actualizada correctamente.
                </p>
              )}

              <div className="mt-6">
                <button
                  type="submit"
                  disabled={changePasswordMutation.isPending}
                  className="rounded-md bg-[#d79921] px-6 py-2 text-sm font-medium text-[#fbf1c7] hover:bg-[#b57614] disabled:opacity-50"
                >
                  {changePasswordMutation.isPending
                    ? "Cambiando..."
                    : "Cambiar contraseña"}
                </button>
              </div>
            </form>
          </div>

          {/* Categories Section */}
          <div className="border-t border-[#d5c4a1] pt-6 mt-6">
            <h2 className="text-base font-semibold text-[#d79921] mb-4">
              Categorías de Activos
            </h2>

            {catLoading ? (
              <LoadingSpinner />
            ) : (
              <>
                {categories.length === 0 ? (
                  <p className="text-sm text-[#928374] mb-4">
                    No hay categorías configuradas.
                  </p>
                ) : (
                  <ul className="mb-4 space-y-2">
                    {categories.map((cat, i) => (
                      <li key={cat} className="flex items-center justify-between rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-2 text-sm text-[#3c3836]">
                        <span>{cat}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveCategory(i)}
                          disabled={updateCategoriesMutation.isPending}
                          className="text-[#cc241d] hover:underline text-xs disabled:opacity-50"
                        >
                          Eliminar
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newCategory}
                    onChange={(e) => { setNewCategory(e.target.value); setCatError(undefined); }}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAddCategory(); } }}
                    placeholder="Nueva categoría"
                    className="flex-1 rounded-md border border-[#d5c4a1] bg-[#fbf1c7] px-3 py-2 text-sm text-[#3c3836] focus:outline-none focus:ring-2 focus:ring-[#d79921]"
                  />
                  <button
                    type="button"
                    onClick={handleAddCategory}
                    disabled={updateCategoriesMutation.isPending}
                    className="rounded-md bg-[#d79921] px-4 py-2 text-sm font-medium text-[#fbf1c7] hover:bg-[#b57614] disabled:opacity-50"
                  >
                    Agregar
                  </button>
                </div>

                {catError && (
                  <p className="mt-2 text-sm text-[#cc241d]">{catError}</p>
                )}
                {catSuccess && (
                  <p className="mt-2 text-sm text-[#98971a]">Categoría guardada.</p>
                )}
              </>
            )}
          </div>
        </div>
      ) : null}
      </div>
    </AppLayout>
  );
}
