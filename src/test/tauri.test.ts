import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getAppDataPath,
  openFilePicker,
  openFolderPicker,
  saveFilePicker,
} from "../lib/tauri";

// Mock @tauri-apps/api/core
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

// Mock @tauri-apps/plugin-dialog
vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(),
  save: vi.fn(),
}));

import { invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";

describe("tauri.ts — Tauri OS commands", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("getAppDataPath", () => {
    it("invokes get_app_data_path command", async () => {
      const mockPath = "/home/user/.local/share/com.sgaf.app";
      vi.mocked(invoke).mockResolvedValueOnce(mockPath);

      const result = await getAppDataPath();

      expect(invoke).toHaveBeenCalledWith("get_app_data_path");
      expect(result).toBe(mockPath);
    });

    it("returns app data directory path from Tauri", async () => {
      const expectedPath = "C:\\Users\\User\\AppData\\Local\\com.sgaf.app";
      vi.mocked(invoke).mockResolvedValueOnce(expectedPath);

      const result = await getAppDataPath();

      expect(result).toBe(expectedPath);
    });

    it("handles invoke errors", async () => {
      vi.mocked(invoke).mockRejectedValueOnce(new Error("Command failed"));

      await expect(getAppDataPath()).rejects.toThrow("Command failed");
    });
  });

  describe("openFilePicker", () => {
    it("opens file picker with default options", async () => {
      const mockPath = "/home/user/document.pdf";
      vi.mocked(open).mockResolvedValueOnce(mockPath);

      const result = await openFilePicker();

      expect(open).toHaveBeenCalledWith({
        title: undefined,
        filters: undefined,
        multiple: false,
        directory: false,
      });
      expect(result).toBe(mockPath);
    });

    it("opens file picker with custom title and filters", async () => {
      const mockPath = "/home/user/assets.csv";
      vi.mocked(open).mockResolvedValueOnce(mockPath);

      const result = await openFilePicker({
        title: "Import Assets",
        filters: [{ name: "CSV", extensions: ["csv"] }],
      });

      expect(open).toHaveBeenCalledWith({
        title: "Import Assets",
        filters: [{ name: "CSV", extensions: ["csv"] }],
        multiple: false,
        directory: false,
      });
      expect(result).toBe(mockPath);
    });

    it("returns null when file picker is cancelled", async () => {
      vi.mocked(open).mockResolvedValueOnce(null);

      const result = await openFilePicker();

      expect(result).toBeNull();
    });

    it("handles array return from open() by returning first item", async () => {
      vi.mocked(open).mockResolvedValueOnce(["/file1.txt", "/file2.txt"]);

      const result = await openFilePicker();

      // The function checks `typeof result === "string"` so returns null for arrays
      expect(result).toBeNull();
    });
  });

  describe("openFolderPicker", () => {
    it("opens folder picker", async () => {
      const mockPath = "/home/user/exports";
      vi.mocked(open).mockResolvedValueOnce(mockPath);

      const result = await openFolderPicker();

      expect(open).toHaveBeenCalledWith({
        title: undefined,
        multiple: false,
        directory: true,
      });
      expect(result).toBe(mockPath);
    });

    it("opens folder picker with custom title", async () => {
      const mockPath = "/mnt/backup";
      vi.mocked(open).mockResolvedValueOnce(mockPath);

      const result = await openFolderPicker({
        title: "Select backup folder",
      });

      expect(open).toHaveBeenCalledWith({
        title: "Select backup folder",
        multiple: false,
        directory: true,
      });
      expect(result).toBe(mockPath);
    });

    it("returns null when folder picker cancelled", async () => {
      vi.mocked(open).mockResolvedValueOnce(null);

      const result = await openFolderPicker();

      expect(result).toBeNull();
    });
  });

  describe("saveFilePicker", () => {
    it("opens save dialog with default options", async () => {
      const mockPath = "/home/user/export.pdf";
      vi.mocked(save).mockResolvedValueOnce(mockPath);

      const result = await saveFilePicker();

      expect(save).toHaveBeenCalledWith({
        title: undefined,
        defaultPath: undefined,
        filters: undefined,
      });
      expect(result).toBe(mockPath);
    });

    it("opens save dialog with custom options", async () => {
      const mockPath = "/home/user/report-2026.pdf";
      vi.mocked(save).mockResolvedValueOnce(mockPath);

      const result = await saveFilePicker({
        title: "Save report",
        defaultPath: "report-2026",
        filters: [{ name: "PDF", extensions: ["pdf"] }],
      });

      expect(save).toHaveBeenCalledWith({
        title: "Save report",
        defaultPath: "report-2026",
        filters: [{ name: "PDF", extensions: ["pdf"] }],
      });
      expect(result).toBe(mockPath);
    });

    it("returns null when save dialog cancelled", async () => {
      vi.mocked(save).mockResolvedValueOnce(null);

      const result = await saveFilePicker();

      expect(result).toBeNull();
    });

    it("handles save errors gracefully", async () => {
      vi.mocked(save).mockRejectedValueOnce(new Error("Permission denied"));

      await expect(saveFilePicker({ title: "Save file" })).rejects.toThrow(
        "Permission denied",
      );
    });
  });
});
