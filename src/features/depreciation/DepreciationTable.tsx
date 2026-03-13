/**
 * DepreciationTable — display depreciation results in a formatted table (AC4).
 *
 * Monetary values arrive as 4-decimal-place strings from the API — displayed as-is.
 * Monetary columns use IBM Plex Mono for vertical alignment.
 * Depreciation method shown as human-readable Spanish label.
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { DepreciationResult } from "@/types/depreciation";

// ---------------------------------------------------------------------------
// Method labels
// ---------------------------------------------------------------------------

const METHOD_LABELS: Record<string, string> = {
  straight_line: "Lineal",
  sum_of_digits: "Suma de Dígitos",
  declining_balance: "Saldo Decreciente",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface DepreciationTableProps {
  rows: DepreciationResult[];
}

export default function DepreciationTable({ rows }: DepreciationTableProps) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Código</TableHead>
            <TableHead>Descripción</TableHead>
            <TableHead>Método</TableHead>
            <TableHead className="text-right">Valor Libro Apertura</TableHead>
            <TableHead className="text-right">Cargo Mensual</TableHead>
            <TableHead className="text-right">Dep. Acumulada</TableHead>
            <TableHead className="text-right">Valor Libro Neto</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.result_id}>
              <TableCell>{row.code}</TableCell>
              <TableCell>{row.description}</TableCell>
              <TableCell>
                {METHOD_LABELS[row.depreciation_method] ?? row.depreciation_method}
              </TableCell>
              <TableCell className="text-right font-[IBM_Plex_Mono,monospace]">
                {row.opening_book_value}
              </TableCell>
              <TableCell className="text-right font-[IBM_Plex_Mono,monospace]">
                {row.depreciation_amount}
              </TableCell>
              <TableCell className="text-right font-[IBM_Plex_Mono,monospace]">
                {row.accumulated_depreciation}
              </TableCell>
              <TableCell className="text-right font-[IBM_Plex_Mono,monospace]">
                {row.book_value}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
