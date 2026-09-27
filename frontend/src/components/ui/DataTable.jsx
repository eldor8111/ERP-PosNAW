const alignCls = (align) =>
  align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left';

/**
 * Umumiy jadval o'rovchisi (wrapper) — Ombor/Hisobotlar sahifalaridagi
 * hozirgi qo'lda yozilgan <table> naqshini token'lar bilan qayta ishlatadi.
 *
 * columns: [{ key, label, align?, numeric?, render?(row) }]
 * rows: object[]
 */
export function DataTable({ columns, rows, rowKey = (r) => r.id, emptyText = "Ma'lumot topilmadi", onRowClick }) {
  return (
    <div className="bg-surface rounded-2xl border border-line overflow-hidden shadow-sm">
      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="bg-surface-sunken border-b border-line">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`px-4 py-3 text-xs font-semibold text-ink-500 uppercase tracking-wider ${alignCls(col.align)}`}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={`hover:bg-surface-sunken/60 transition-colors ${onRowClick ? 'cursor-pointer' : ''}`}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`px-4 py-3 text-sm text-ink-900 ${col.numeric ? 'tabular-nums' : ''} ${alignCls(col.align)}`}
                  >
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-6 py-16 text-center text-sm text-ink-300">
                  {emptyText}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
