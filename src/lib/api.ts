/// HTTP client for Flask API communication.
/// Port is set dynamically at startup when backend-ready event fires.

export class ApiError extends Error {
  status: number;
  field?: string;
  errorCode?: string;

  constructor(
    message: string,
    status: number,
    field?: string,
    errorCode?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.field = field;
    this.errorCode = errorCode;
  }
}

let apiPort: number = parseInt(import.meta.env.VITE_API_PORT ?? "5000", 10);

export function setApiPort(port: number): void {
  apiPort = port;
}

export function getBaseUrl(): string {
  return `http://127.0.0.1:${apiPort}/api/v1`;
}

interface FetchOptions extends RequestInit {
  token?: string;
}

/// Core fetch wrapper — adds Authorization header if token is provided.
/// All Flask business calls go through here, never through Tauri invoke().
export async function apiFetch<T>(
  path: string,
  options: FetchOptions = {},
): Promise<T> {
  const { token, ...fetchOptions } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${getBaseUrl()}${path}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    // Global 401 handler: clear stale token so PrivateRoute redirects to /login
    if (response.status === 401 && token) {
      const { useAppStore } = await import("../store/appStore");
      useAppStore.getState().clearToken();
    }

    let errorMessage = `Request failed: ${response.status}`;
    let field: string | undefined;
    let errorCode: string | undefined;
    try {
      const error = await response.json();
      errorMessage = error.message ?? error.error ?? errorMessage;
      field = error.field;
      errorCode = error.error;
    } catch {
      // Response is not JSON (e.g., 500 HTML error page)
      // Keep the generic HTTP error message
    }
    throw new ApiError(errorMessage, response.status, field, errorCode);
  }

  // Handle no-content responses (e.g., 204 DELETE)
  if (response.status === 204) {
    return undefined as T;
  }

  // Validate response is JSON before parsing
  const contentType = response.headers.get("content-type");
  if (!contentType?.includes("application/json")) {
    throw new Error(
      `Expected JSON response, got ${contentType ?? "unknown content-type"}`,
    );
  }

  return response.json() as Promise<T>;
}

/// Trigger depreciation calculation for a given period.
/// POST /api/v1/depreciation/
export async function triggerDepreciation(
  periodMonth: number,
  periodYear: number,
  token: string,
): Promise<import("../types/depreciation").DepreciationResponse> {
  return apiFetch<import("../types/depreciation").DepreciationResponse>(
    "/depreciation/",
    {
      method: "POST",
      body: JSON.stringify({
        period_month: periodMonth,
        period_year: periodYear,
      }),
      token,
    },
  );
}

/// Retrieve stored depreciation results for a given period.
/// GET /api/v1/depreciation/?period_month=M&period_year=Y
export async function getDepreciationResults(
  periodMonth: number,
  periodYear: number,
  token: string,
): Promise<import("../types/depreciation").DepreciationResponse> {
  return apiFetch<import("../types/depreciation").DepreciationResponse>(
    `/depreciation/?period_month=${periodMonth}&period_year=${periodYear}`,
    { token },
  );
}

/// Generate a NIIF PDF report. Returns PDF bytes as a Blob.
/// Note: Cannot use apiFetch() — it always calls response.json().
/// Uses raw fetch with Authorization header from token.
export async function generatePdfReport(
  params: {
    report_type: "per_asset" | "monthly_summary" | "asset_register";
    asset_id?: number;
    period_month?: number;
    period_year?: number;
  },
  token: string,
): Promise<Blob> {
  const response = await fetch(`${getBaseUrl()}/reports/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    // Mirror apiFetch's global 401 handler: clear stale token so PrivateRoute redirects
    if (response.status === 401 && token) {
      const { useAppStore } = await import("../store/appStore");
      useAppStore.getState().clearToken();
    }
    let message = `Request failed: ${response.status}`;
    try {
      const err = await response.json();
      message = err.message ?? err.error ?? message;
    } catch {
      /* not JSON */
    }
    throw new ApiError(message, response.status);
  }
  return response.blob();
}

/// GET /api/v1/reports/status — PDF generation status for a period.
export async function getReportStatus(
  periodMonth: number,
  periodYear: number,
  token: string,
): Promise<{ monthly_summary_generated_at: string | null }> {
  return apiFetch<{ data: { monthly_summary_generated_at: string | null } }>(
    `/reports/status?period_month=${periodMonth}&period_year=${periodYear}`,
    { token },
  ).then((res) => res.data);
}

/// GET /api/v1/maintenance/?asset_id=<id> — List maintenance events for an asset.
export async function getMaintenanceEvents(
  assetId: number,
  token: string,
): Promise<{ data: import("../types/maintenance").MaintenanceEvent[]; total: number }> {
  return apiFetch<{
    data: import("../types/maintenance").MaintenanceEvent[];
    total: number;
  }>(`/maintenance/?asset_id=${assetId}`, { token });
}

/// POST /api/v1/maintenance/ — Register a new maintenance event (created directly as completed).
export async function createMaintenanceEvent(
  payload: import("../types/maintenance").CreateMaintenancePayload,
  token: string,
): Promise<{ data: import("../types/maintenance").MaintenanceEvent }> {
  return apiFetch<{ data: import("../types/maintenance").MaintenanceEvent }>(
    "/maintenance/",
    {
      method: "POST",
      body: JSON.stringify(payload),
      token,
    },
  );
}

/// GET /api/v1/config/company — Fetch current company configuration.
export async function getCompanyConfig(
  token: string,
): Promise<{ company_name: string; company_nit: string; logo_path: string | null }> {
  return apiFetch<{
    data: { company_name: string; company_nit: string; logo_path: string | null };
  }>("/config/company", { token }).then((res) => res.data);
}

/// PUT /api/v1/config/company — Update company configuration.
export async function updateCompanyConfig(
  payload: { company_name: string; company_nit: string; logo_path: string | null },
  token: string,
): Promise<{ ok: boolean }> {
  return apiFetch<{ data: { ok: boolean } }>("/config/company", {
    method: "PUT",
    body: JSON.stringify(payload),
    token,
  }).then((res) => res.data);
}

/// POST /api/v1/config/change-password — Change application password.
export async function changePassword(
  payload: { current_password: string; new_password: string; new_password_confirm: string },
  token: string,
): Promise<{ ok: boolean }> {
  return apiFetch<{ data: { ok: boolean } }>("/config/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
    token,
  }).then((res) => res.data);
}

/// Retrieve all depreciation results for a specific asset across all calculated periods.
/// GET /api/v1/depreciation/assets/{assetId}
export async function getAssetDepreciationHistory(
  assetId: number,
  token: string,
): Promise<import("../types/depreciation").AssetDepreciationHistoryResponse> {
  return apiFetch<
    import("../types/depreciation").AssetDepreciationHistoryResponse
  >(`/depreciation/assets/${assetId}`, { token });
}
