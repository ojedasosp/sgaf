import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { convertFileSrc } from "@tauri-apps/api/core";
import { apiFetch } from "../lib/api";
import { openFilePicker } from "../lib/tauri";

type Step = 1 | 2;

interface CompanyInfo {
  company_name: string;
  company_nit: string;
  logo_path: string | null;
}

interface PasswordInfo {
  password: string;
  password_confirm: string;
}

interface FormErrors {
  company_name?: string;
  company_nit?: string;
  password?: string;
  password_confirm?: string;
  submit?: string;
}

export default function SetupWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>(1);
  const [company, setCompany] = useState<CompanyInfo>({
    company_name: "",
    company_nit: "",
    logo_path: null,
  });
  const [passwords, setPasswords] = useState<PasswordInfo>({
    password: "",
    password_confirm: "",
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [setupComplete, setSetupComplete] = useState(false);
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    return () => {
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current);
    };
  }, []);

  // Step 1 validation
  function validateStep1(): FormErrors {
    const errs: FormErrors = {};
    if (!company.company_name.trim()) {
      errs.company_name = "Company name is required";
    }
    if (!company.company_nit.trim()) {
      errs.company_nit = "NIT is required";
    } else if (!/^\d+$/.test(company.company_nit.trim())) {
      errs.company_nit = "NIT must contain only numbers";
    }
    return errs;
  }

  // Step 2 validation
  function validateStep2(): FormErrors {
    const errs: FormErrors = {};
    if (passwords.password.length < 8) {
      errs.password = "Password must be at least 8 characters";
    }
    if (passwords.password !== passwords.password_confirm) {
      errs.password_confirm = "Passwords do not match";
    }
    return errs;
  }

  function handleNext() {
    const errs = validateStep1();
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
    setErrors({});
    setStep(2);
  }

  async function handleLogoSelect() {
    const path = await openFilePicker({
      title: "Select company logo",
      filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg"] }],
    });
    if (path) {
      setCompany((prev) => ({ ...prev, logo_path: path }));
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validateStep2();
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      return;
    }
    setErrors({});
    setIsSubmitting(true);
    try {
      await apiFetch("/config/setup", {
        method: "POST",
        body: JSON.stringify({
          company_name: company.company_name.trim(),
          company_nit: company.company_nit.trim(),
          password: passwords.password,
          password_confirm: passwords.password_confirm,
          logo_path: company.logo_path,
        }),
      });
      setSetupComplete(true);
      // Brief confirmation before navigating to login
      redirectTimerRef.current = setTimeout(() => navigate("/login", { replace: true }), 1500);
    } catch (err) {
      setErrors({
        submit:
          err instanceof Error ? err.message : "Setup failed. Please try again.",
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  if (setupComplete) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="text-center">
          <p className="text-lg font-semibold text-green-600">
            Setup complete. Redirecting to login...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-8 shadow-sm">
        {/* Progress indicator */}
        <p className="mb-6 text-center text-sm text-muted-foreground">
          Step {step} of 2
        </p>

        {step === 1 ? (
          <>
            <h2 className="mb-6 text-2xl font-bold text-foreground">
              Company Information
            </h2>

            <div className="space-y-6">
              {/* Company Name */}
              <div>
                <label
                  htmlFor="company_name"
                  className="mb-1 block text-sm font-medium text-foreground"
                >
                  Company Name (Razón Social){" "}
                  <span className="text-destructive">*</span>
                </label>
                <input
                  id="company_name"
                  type="text"
                  maxLength={100}
                  value={company.company_name}
                  onChange={(e) =>
                    setCompany((prev) => ({
                      ...prev,
                      company_name: e.target.value,
                    }))
                  }
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Mi Empresa S.A.S"
                />
                {errors.company_name && (
                  <p className="mt-1 text-sm text-destructive">
                    {errors.company_name}
                  </p>
                )}
              </div>

              {/* NIT */}
              <div>
                <label
                  htmlFor="company_nit"
                  className="mb-1 block text-sm font-medium text-foreground"
                >
                  NIT <span className="text-destructive">*</span>
                </label>
                <input
                  id="company_nit"
                  type="text"
                  value={company.company_nit}
                  onChange={(e) =>
                    setCompany((prev) => ({
                      ...prev,
                      company_nit: e.target.value,
                    }))
                  }
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="9001234560"
                />
                {errors.company_nit && (
                  <p className="mt-1 text-sm text-destructive">
                    {errors.company_nit}
                  </p>
                )}
              </div>

              {/* Logo Upload (optional) */}
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  Company Logo (optional)
                </label>
                <button
                  type="button"
                  onClick={handleLogoSelect}
                  className="rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground hover:bg-accent"
                >
                  {company.logo_path ? "Change logo" : "Select logo (PNG/JPG)"}
                </button>
                {company.logo_path && (
                  <div className="mt-2">
                    <img
                      src={convertFileSrc(company.logo_path)}
                      alt="Logo preview"
                      className="max-h-16 max-w-[200px] rounded object-contain"
                    />
                  </div>
                )}
              </div>
            </div>

            <div className="mt-8 flex justify-end gap-3">
              <button
                type="button"
                onClick={handleNext}
                className="rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              >
                Next
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            <button
              type="button"
              onClick={() => {
                setErrors({});
                setStep(1);
              }}
              className="mb-4 text-sm text-muted-foreground hover:text-foreground"
            >
              ← Back
            </button>

            <h2 className="mb-6 text-2xl font-bold text-foreground">
              Set Access Password
            </h2>

            <div className="space-y-6">
              {/* Password */}
              <div>
                <label
                  htmlFor="password"
                  className="mb-1 block text-sm font-medium text-foreground"
                >
                  Password <span className="text-destructive">*</span>
                </label>
                <input
                  id="password"
                  type="password"
                  value={passwords.password}
                  onChange={(e) =>
                    setPasswords((prev) => ({
                      ...prev,
                      password: e.target.value,
                    }))
                  }
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  At least 8 characters
                </p>
                {errors.password && (
                  <p className="mt-1 text-sm text-destructive">
                    {errors.password}
                  </p>
                )}
              </div>

              {/* Confirm Password */}
              <div>
                <label
                  htmlFor="password_confirm"
                  className="mb-1 block text-sm font-medium text-foreground"
                >
                  Confirm Password <span className="text-destructive">*</span>
                </label>
                <input
                  id="password_confirm"
                  type="password"
                  value={passwords.password_confirm}
                  onChange={(e) =>
                    setPasswords((prev) => ({
                      ...prev,
                      password_confirm: e.target.value,
                    }))
                  }
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
                {errors.password_confirm && (
                  <p className="mt-1 text-sm text-destructive">
                    {errors.password_confirm}
                  </p>
                )}
              </div>

              {/* Submit error */}
              {errors.submit && (
                <p className="text-sm text-destructive">{errors.submit}</p>
              )}
            </div>

            <div className="mt-8 flex justify-end gap-3">
              <button
                type="submit"
                disabled={isSubmitting}
                className="rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {isSubmitting ? "Setting up..." : "Complete Setup"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
