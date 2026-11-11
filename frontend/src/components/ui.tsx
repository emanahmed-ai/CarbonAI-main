import { type ReactNode, useMemo, useState } from 'react'
import { useI18n } from '../i18n'

export function Card({ title, children, actions, className = '' }: { title?: ReactNode; children: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white shadow-sm ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
          <div className="flex items-center gap-2">{actions}</div>
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  )
}

export function StatCard({ label, value, sub, accent = 'brand' }: { label: ReactNode; value: ReactNode; sub?: ReactNode; accent?: 'brand' | 'amber' | 'sky' | 'rose' }) {
  const accents: Record<string, string> = {
    brand: 'from-brand-600 to-brand-800',
    amber: 'from-amber-500 to-amber-700',
    sky: 'from-sky-500 to-sky-700',
    rose: 'from-rose-500 to-rose-700',
  }
  return (
    <div className={`rounded-xl bg-gradient-to-br ${accents[accent]} p-4 text-white shadow-sm`}>
      <div className="text-xs/5 opacity-80">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      {sub && <div className="mt-1 text-xs opacity-75">{sub}</div>}
    </div>
  )
}

export function Badge({ tone, children }: { tone: 'green' | 'amber' | 'red' | 'gray' | 'blue' | 'purple'; children: ReactNode }) {
  const tones: Record<string, string> = {
    green: 'bg-brand-50 text-brand-700 ring-brand-600/20',
    amber: 'bg-amber-50 text-amber-700 ring-amber-600/20',
    red: 'bg-rose-50 text-rose-700 ring-rose-600/20',
    gray: 'bg-slate-100 text-slate-600 ring-slate-500/20',
    blue: 'bg-sky-50 text-sky-700 ring-sky-600/20',
    purple: 'bg-violet-50 text-violet-700 ring-violet-600/20',
  }
  return <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}>{children}</span>
}

export function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n()
  const map: Record<string, [any, string]> = {
    approved: ['green', t('approved')], submitted: ['blue', t('submitted')], rejected: ['red', t('rejected')],
    withdrawn: ['gray', t('withdrawn')], calculated: ['green', t('calculated')], needs_review: ['amber', 'needs review'],
    needs_factor: ['amber', 'needs factor'], needs_date: ['amber', 'needs date'], rejected_unit: ['red', 'rejected unit'],
    verified: ['green', 'verified'], unverified: ['gray', 'unverified'], pending_review: ['amber', 'pending review'],
    superseded: ['gray', 'superseded'], suggested: ['blue', 'suggested'], confirmed: ['green', 'confirmed'],
    undetermined: ['amber', 'undetermined'], planned: ['gray', t('planned')], in_progress: ['blue', t('inProgress')],
    done: ['green', t('done')], cancelled: ['red', t('cancelled')],
  }
  const [tone, label] = map[status] ?? ['gray', status]
  return <Badge tone={tone}>{label}</Badge>
}

export function Select({ label, value, onChange, options, className = '' }: {
  label?: string; value: string; onChange: (v: string) => void
  options: { value: string; label: string }[]; className?: string
}) {
  return (
    <label className={`block ${className}`}>
      {label && <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>}
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100">
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  )
}

export function Input({ label, value, onChange, type = 'text', placeholder, step, className = '', required }: {
  label?: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string
  step?: string; className?: string; required?: boolean
}) {
  return (
    <label className={`block ${className}`}>
      {label && <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>}
      <input type={type} value={value} placeholder={placeholder} step={step} required={required}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" />
    </label>
  )
}

export function Textarea({ label, value, onChange, rows = 3, className = '' }: { label?: string; value: string; onChange: (v: string) => void; rows?: number; className?: string }) {
  return (
    <label className={`block ${className}`}>
      {label && <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>}
      <textarea value={value} rows={rows} onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100" />
    </label>
  )
}

export function Button({ children, onClick, variant = 'primary', type = 'button', disabled, className = '' }: {
  children: ReactNode; onClick?: () => void; variant?: 'primary' | 'ghost' | 'danger' | 'outline'; type?: 'button' | 'submit'
  disabled?: boolean; className?: string
}) {
  const styles: Record<string, string> = {
    primary: 'bg-brand-600 text-white hover:bg-brand-700 shadow-sm',
    ghost: 'text-slate-600 hover:bg-slate-100',
    danger: 'bg-rose-600 text-white hover:bg-rose-700',
    outline: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`inline-flex items-center justify-center gap-1 rounded-lg px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${className}`}>
      {children}
    </button>
  )
}

export function Modal({ open, title, onClose, children, wide }: { open: boolean; title: ReactNode; onClose: () => void; children: ReactNode; wide?: boolean }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 sm:items-center" onMouseDown={onClose}>
      <div className={`w-full ${wide ? 'max-w-3xl' : 'max-w-lg'} rounded-xl bg-white shadow-xl`} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h3 className="font-semibold text-slate-800">{title}</h3>
          <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100">✕</button>
        </div>
        <div className="max-h-[75vh] overflow-y-auto p-4">{children}</div>
      </div>
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 p-8 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
      {label}
    </div>
  )
}

export function EmptyState({ text }: { text: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">{text}</div>
}

/** Sortable, searchable data table. */
export function DataTable<T extends Record<string, any>>({
  columns, rows, pageSize = 15, onRowClick, empty,
}: {
  columns: { key: string; label: ReactNode; render?: (row: T) => ReactNode; sortable?: boolean }[]
  rows: T[]; pageSize?: number; onRowClick?: (row: T) => void; empty?: ReactNode
}) {
  const { t } = useI18n()
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null)
  const filtered = useMemo(() => {
    let out = rows
    if (q.trim()) {
      const s = q.toLowerCase()
      out = rows.filter((r) => columns.some((c) => String(r[c.key] ?? '').toLowerCase().includes(s)))
    }
    if (sort) {
      out = [...out].sort((a, b) => {
        const va = a[sort.key], vb = b[sort.key]
        if (va == null) return 1
        if (vb == null) return -1
        const n = Number(va) - Number(vb)
        return (isNaN(n) ? String(va).localeCompare(String(vb)) : n) * sort.dir
      })
    }
    return out
  }, [rows, q, sort, columns])
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const p = Math.min(page, pages)
  const shown = filtered.slice((p - 1) * pageSize, p * pageSize)
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} placeholder={t('search')}
          className="w-56 rounded-lg border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-brand-500" />
        <span className="text-xs text-slate-400">{filtered.length}</span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              {columns.map((c) => (
                <th key={c.key} onClick={() => c.sortable !== false && setSort((s) => (s?.key === c.key ? { key: c.key, dir: s.dir === 1 ? -1 : 1 } : { key: c.key, dir: 1 }))}
                  className="cursor-pointer whitespace-nowrap px-3 py-2 text-start text-xs font-semibold text-slate-500 select-none hover:text-slate-700">
                  {c.label}{sort?.key === c.key ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {shown.map((r, i) => (
              <tr key={i} onClick={() => onRowClick?.(r)} className={onRowClick ? 'cursor-pointer hover:bg-brand-50/50' : 'hover:bg-slate-50'}>
                {columns.map((c) => (
                  <td key={c.key} className="whitespace-nowrap px-3 py-2 text-slate-700">{c.render ? c.render(r) : String(r[c.key] ?? '—')}</td>
                ))}
              </tr>
            ))}
            {shown.length === 0 && (
              <tr><td colSpan={columns.length} className="px-3 py-8 text-center text-sm text-slate-400">{empty ?? t('noData')}</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="mt-2 flex items-center justify-end gap-1 text-sm">
          <Button variant="outline" onClick={() => setPage(p - 1)} disabled={p <= 1}>‹</Button>
          <span className="px-2 text-xs text-slate-500">{p} / {pages}</span>
          <Button variant="outline" onClick={() => setPage(p + 1)} disabled={p >= pages}>›</Button>
        </div>
      )}
    </div>
  )
}

export const fmtKg = (v: string | number | null | undefined, digits = 0) =>
  v == null ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: digits })
