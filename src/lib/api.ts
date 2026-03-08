/// HTTP client for Flask API communication.
/// Port is set dynamically at startup when backend-ready event fires.

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
  options: FetchOptions = {}
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
    let errorMessage = `Request failed: ${response.status}`;
    try {
      const error = await response.json();
      errorMessage = error.message ?? error.error ?? errorMessage;
    } catch {
      // Response is not JSON (e.g., 500 HTML error page)
      // Keep the generic HTTP error message
    }
    throw new Error(errorMessage);
  }

  // Validate response is JSON before parsing
  const contentType = response.headers.get("content-type");
  if (!contentType?.includes("application/json")) {
    throw new Error(
      `Expected JSON response, got ${contentType ?? "unknown content-type"}`
    );
  }

  return response.json() as Promise<T>;
}
