/** Shared number/date formatting so every screen reads the same way. */

export const nf = new Intl.NumberFormat('en-GB')
export const nf2 = new Intl.NumberFormat('en-GB', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export function int(value) {
  return Number.isFinite(value) ? nf.format(Math.round(value)) : '--'
}

export function dec(value, digits = 3) {
  return Number.isFinite(value) ? value.toFixed(digits) : '--'
}

export function pct(value, digits = 1) {
  return Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : '--'
}

export function money(value, currency = 'GBP') {
  if (!Number.isFinite(value)) return '--'
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency,
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value)
}

export function datetime(value) {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
}

export function day(value) {
  if (!value) return '--'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? String(value).slice(0, 10)
    : date.toLocaleDateString('en-GB', { dateStyle: 'medium' })
}

/** Download an array of flat objects as a CSV file. */
export function downloadCsv(filename, rows) {
  if (!rows?.length) return
  const columns = Object.keys(rows[0])
  const escape = (value) => {
    const text = value === null || value === undefined ? '' : String(value)
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  const csv = [
    columns.join(','),
    ...rows.map((row) => columns.map((c) => escape(row[c])).join(',')),
  ].join('\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
