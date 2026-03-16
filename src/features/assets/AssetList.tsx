/**
 * AssetList — FR4, FR7: Asset list with real-time search, status/category filters,
 * color-coded status badges, and sortable columns.
 *
 * Uses TanStack Table v8 for client-side filtering/sorting (all assets loaded
 * at once — ≤500 assets per NFR4). Filtering is entirely in-browser.
 */

import {
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useGetAssets } from "@/hooks/useAssets";
import type { Asset, AssetStatus } from "@/types/asset";
import AppLayout from "@/components/layout/AppLayout";

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<AssetStatus, { label: string; className: string }> =
  {
    active: {
      label: "Activo",
      className: "bg-[#98971a]/10 text-[#98971a] border border-[#98971a]/20",
    },
    in_maintenance: {
      label: "En Mantenimiento",
      className: "bg-[#d79921]/10 text-[#d79921] border border-[#d79921]/20",
    },
    retired: {
      label: "Retirado",
      className: "bg-[#7c6f64]/10 text-[#7c6f64] border border-[#7c6f64]/20",
    },
  };

function StatusBadge({ status }: { status: AssetStatus }) {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    className: "bg-[#928374]/10 text-[#928374] border border-[#928374]/20",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${config.className}`}
    >
      {config.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Date formatter: "YYYY-MM-DD" → "DD/MM/YYYY"
// ---------------------------------------------------------------------------
function formatDate(iso: string): string {
  const parts = iso.split("-");
  if (parts.length !== 3) return iso;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

// ---------------------------------------------------------------------------
// Currency formatter: "1200.0000" → "$1.200,0000" (LATAM convention)
// ---------------------------------------------------------------------------
function formatCurrency(value: string): string {
  const num = parseFloat(value);
  if (isNaN(num)) return value;
  const [intPart, decPart] = value.split(".");
  const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `$${formattedInt},${decPart ?? "0000"}`;
}

// ---------------------------------------------------------------------------
// Column definitions (memoised outside component for stable reference)
// ---------------------------------------------------------------------------

const COLUMNS: ColumnDef<Asset>[] = [
  {
    accessorKey: "code",
    header: "Código",
    cell: ({ getValue }) => (
      <span className="font-medium text-[#3c3836]">{getValue<string>()}</span>
    ),
  },
  {
    accessorKey: "description",
    header: "Descripción",
    cell: ({ getValue }) => (
      <span className="text-[#3c3836]">{getValue<string>()}</span>
    ),
  },
  {
    accessorKey: "category",
    header: "Categoría",
    filterFn: "equalsString",
    cell: ({ getValue }) => (
      <span className="text-[#665c54]">{getValue<string>()}</span>
    ),
  },
  {
    accessorKey: "acquisition_date",
    header: "Fecha Adquisición",
    enableGlobalFilter: false,
    cell: ({ getValue }) => (
      <span className="text-[#665c54] text-sm">
        {formatDate(getValue<string>())}
      </span>
    ),
  },
  {
    accessorKey: "status",
    header: "Estado",
    filterFn: "equalsString",
    enableGlobalFilter: false,
    cell: ({ getValue }) => <StatusBadge status={getValue<AssetStatus>()} />,
  },
  {
    accessorKey: "historical_cost",
    header: "Costo Histórico",
    enableGlobalFilter: false,
    sortingFn: (rowA, rowB) =>
      parseFloat(rowA.getValue("historical_cost")) -
      parseFloat(rowB.getValue("historical_cost")),
    cell: ({ getValue }) => (
      <span className="font-mono text-right block text-[#3c3836]">
        {formatCurrency(getValue<string>())}
      </span>
    ),
  },
];

// ---------------------------------------------------------------------------
// Skeleton loader row
// ---------------------------------------------------------------------------
function SkeletonRow() {
  return (
    <TableRow>
      {COLUMNS.map((_, i) => (
        <TableCell key={i}>
          <div className="h-4 rounded bg-[#d5c4a1] animate-pulse" />
        </TableCell>
      ))}
    </TableRow>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function AssetList() {
  const navigate = useNavigate();
  const { data: assets, isLoading, isError, refetch } = useGetAssets();

  // Filter state
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [sorting, setSorting] = useState<SortingState>([
    { id: "acquisition_date", desc: true },
  ]);

  // Search with 300ms debounce
  const [searchInput, setSearchInput] = useState("");
  const [globalFilter, setGlobalFilter] = useState("");
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  function handleSearchChange(value: string) {
    setSearchInput(value);
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => setGlobalFilter(value), 300);
  }

  function clearSearch() {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    setSearchInput("");
    setGlobalFilter("");
  }

  // Derive unique categories from loaded data
  const categories = useMemo(() => {
    if (!assets) return [];
    return Array.from(new Set(assets.map((a) => a.category))).sort();
  }, [assets]);

  // Current filter values
  const statusFilter =
    (columnFilters.find((f) => f.id === "status")?.value as string) ?? "";
  const categoryFilter =
    (columnFilters.find((f) => f.id === "category")?.value as string) ?? "";

  function setStatusFilter(value: string) {
    setColumnFilters((prev) => {
      const others = prev.filter((f) => f.id !== "status");
      return value ? [...others, { id: "status", value }] : others;
    });
  }

  function setCategoryFilter(value: string) {
    setColumnFilters((prev) => {
      const others = prev.filter((f) => f.id !== "category");
      return value ? [...others, { id: "category", value }] : others;
    });
  }

  function clearAllFilters() {
    setColumnFilters([]);
    clearSearch();
  }

  const hasActiveFilters = columnFilters.length > 0 || globalFilter.length > 0;

  // TanStack Table
  const table = useReactTable({
    data: assets ?? [],
    columns: COLUMNS,
    state: { sorting, columnFilters, globalFilter },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    globalFilterFn: "includesString",
  });

  const filteredRows = table.getRowModel().rows;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <AppLayout>
      <div className="flex flex-col gap-4 p-6 bg-[#fbf1c7] min-h-screen">
        {/* Page header — Task 7 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-[#3c3836]">Activos</h1>
            {assets !== undefined && (
              <span className="inline-flex items-center rounded-full bg-[#d5c4a1] px-2.5 py-0.5 text-xs font-medium text-[#665c54]">
                {assets.length}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => navigate("/assets/new")}
            className="rounded-md bg-[#458588] px-4 py-2 text-sm font-medium text-white hover:bg-[#458588]/90"
          >
            + Nuevo Activo
          </button>
        </div>

        {/* Search + Filter controls */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Search input */}
          <div className="relative">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="Buscar por código, nombre o categoría..."
              className="w-72 rounded-md border border-[#bdae93] bg-[#f2e5bc] px-3 py-1.5 text-sm text-[#3c3836] placeholder:text-[#7c6f64] focus:outline-none focus:ring-1 focus:ring-[#458588]"
            />
            {searchInput && (
              <button
                type="button"
                onClick={clearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[#7c6f64] hover:text-[#3c3836]"
                aria-label="Limpiar búsqueda"
              >
                ×
              </button>
            )}
          </div>

          {/* Status filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-[#bdae93] bg-[#f2e5bc] px-3 py-1.5 text-sm text-[#3c3836] focus:outline-none focus:ring-1 focus:ring-[#458588]"
            aria-label="Filtrar por estado"
          >
            <option value="">Todos los estados</option>
            <option value="active">Activo</option>
            <option value="in_maintenance">En Mantenimiento</option>
            <option value="retired">Retirado</option>
          </select>

          {/* Category filter */}
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="rounded-md border border-[#bdae93] bg-[#f2e5bc] px-3 py-1.5 text-sm text-[#3c3836] focus:outline-none focus:ring-1 focus:ring-[#458588]"
            aria-label="Filtrar por categoría"
          >
            <option value="">Todas las categorías</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>

        {/* Active filter badges */}
        {hasActiveFilters && (
          <div className="flex flex-wrap items-center gap-2">
            {globalFilter && (
              <span className="inline-flex items-center gap-1 rounded-full bg-[#d5c4a1] px-2.5 py-0.5 text-xs text-[#665c54]">
                Búsqueda: {globalFilter}
                <button
                  type="button"
                  onClick={clearSearch}
                  className="ml-1 hover:text-[#3c3836]"
                  aria-label="Quitar filtro de búsqueda"
                >
                  ×
                </button>
              </span>
            )}
            {statusFilter && (
              <span className="inline-flex items-center gap-1 rounded-full bg-[#d5c4a1] px-2.5 py-0.5 text-xs text-[#665c54]">
                Estado:{" "}
                {STATUS_CONFIG[statusFilter as AssetStatus]?.label ??
                  statusFilter}
                <button
                  type="button"
                  onClick={() => setStatusFilter("")}
                  className="ml-1 hover:text-[#3c3836]"
                  aria-label="Quitar filtro de estado"
                >
                  ×
                </button>
              </span>
            )}
            {categoryFilter && (
              <span className="inline-flex items-center gap-1 rounded-full bg-[#d5c4a1] px-2.5 py-0.5 text-xs text-[#665c54]">
                Categoría: {categoryFilter}
                <button
                  type="button"
                  onClick={() => setCategoryFilter("")}
                  className="ml-1 hover:text-[#3c3836]"
                  aria-label="Quitar filtro de categoría"
                >
                  ×
                </button>
              </span>
            )}
            <button
              type="button"
              onClick={clearAllFilters}
              className="text-xs text-[#665c54] hover:text-[#3c3836] underline"
            >
              Limpiar filtros
            </button>
          </div>
        )}

        {/* Table */}
        <div className="rounded-md border border-[#d5c4a1] bg-[#f2e5bc]">
          <Table>
            <TableHeader>
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow
                  key={headerGroup.id}
                  className="border-b border-[#d5c4a1] bg-[#ebdbb2]"
                >
                  {headerGroup.headers.map((header) => {
                    const canSort = header.column.getCanSort();
                    const sorted = header.column.getIsSorted();
                    return (
                      <TableHead
                        key={header.id}
                        className="text-[#665c54] font-medium py-3 px-4"
                        style={{ cursor: canSort ? "pointer" : "default" }}
                        onClick={
                          canSort
                            ? header.column.getToggleSortingHandler()
                            : undefined
                        }
                      >
                        <span className="inline-flex items-center gap-1">
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          {canSort && (
                            <span className="text-[#bdae93]">
                              {sorted === "asc"
                                ? "↑"
                                : sorted === "desc"
                                  ? "↓"
                                  : "↕"}
                            </span>
                          )}
                        </span>
                      </TableHead>
                    );
                  })}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {/* Loading state: skeleton rows */}
              {isLoading &&
                Array.from({ length: 5 }).map((_, i) => (
                  <SkeletonRow key={i} />
                ))}

              {/* Error state */}
              {isError && (
                <TableRow>
                  <TableCell
                    colSpan={COLUMNS.length}
                    className="text-center py-12 text-[#cc241d]"
                  >
                    No se pudieron cargar los activos.{" "}
                    <button
                      type="button"
                      onClick={() => refetch()}
                      className="underline hover:no-underline"
                    >
                      Reintentar
                    </button>
                  </TableCell>
                </TableRow>
              )}

              {/* Empty state — no assets at all */}
              {!isLoading && !isError && assets?.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={COLUMNS.length}
                    className="text-center py-16"
                  >
                    <p className="text-[#665c54] mb-4">
                      Aún no has registrado activos.
                    </p>
                    <button
                      type="button"
                      onClick={() => navigate("/assets/new")}
                      className="rounded-md bg-[#458588] px-4 py-2 text-sm font-medium text-white hover:bg-[#458588]/90"
                    >
                      + Registrar primer activo
                    </button>
                  </TableCell>
                </TableRow>
              )}

              {/* Empty state — filters active, no results */}
              {!isLoading &&
                !isError &&
                assets !== undefined &&
                assets.length > 0 &&
                filteredRows.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={COLUMNS.length}
                      className="text-center py-16"
                    >
                      <p className="text-[#665c54] mb-4">
                        No se encontraron activos con los filtros aplicados.
                      </p>
                      <button
                        type="button"
                        onClick={clearAllFilters}
                        className="text-sm text-[#665c54] hover:text-[#3c3836] underline"
                      >
                        Limpiar filtros
                      </button>
                    </TableCell>
                  </TableRow>
                )}

              {/* Data rows */}
              {!isLoading &&
                !isError &&
                filteredRows.map((row) => (
                  <TableRow
                    key={row.id}
                    className="border-b border-[#d5c4a1] cursor-pointer hover:bg-[#ebdbb2] focus:bg-[#ebdbb2] focus:outline-none py-3"
                    tabIndex={0}
                    role="link"
                    onClick={() => navigate(`/assets/${row.original.asset_id}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        navigate(`/assets/${row.original.asset_id}`);
                      }
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id} className="py-3 px-4">
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </AppLayout>
  );
}
