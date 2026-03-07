/// Tauri invoke() wrappers — OS-level operations only.
/// Business logic goes through apiFetch() to Flask, not through these wrappers.
import { invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";

/// Returns the OS app data directory for SGAF (e.g. ~/.local/share/com.sgaf.app)
export async function getAppDataPath(): Promise<string> {
  return invoke<string>("get_app_data_path");
}

/// Opens a file picker dialog. Returns selected path or null if cancelled.
export async function openFilePicker(options?: {
  title?: string;
  filters?: Array<{ name: string; extensions: string[] }>;
}): Promise<string | null> {
  const result = await open({
    title: options?.title,
    filters: options?.filters,
    multiple: false,
    directory: false,
  });
  return typeof result === "string" ? result : null;
}

/// Opens a folder picker dialog. Returns selected path or null if cancelled.
export async function openFolderPicker(options?: {
  title?: string;
}): Promise<string | null> {
  const result = await open({
    title: options?.title,
    multiple: false,
    directory: true,
  });
  return typeof result === "string" ? result : null;
}

/// Opens a save file dialog. Returns target path or null if cancelled.
export async function saveFilePicker(options?: {
  title?: string;
  defaultPath?: string;
  filters?: Array<{ name: string; extensions: string[] }>;
}): Promise<string | null> {
  return save({
    title: options?.title,
    defaultPath: options?.defaultPath,
    filters: options?.filters,
  });
}
