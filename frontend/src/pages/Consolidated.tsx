import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'
import { Card, Select, Spinner, StatCard, fmtKg } from '../components/ui'
import { useI18n } from '../i18n'

type Consol = {
  year: number | null
  total_kg_co2e: string
  total_t_co2e: string
  by_scope_kg: Record<string, string>
  monthly_kg: Record<string, string>
  facilities: { facility_id: number; facility_name: string; total_kg_co2e: string; submissions: number; last_approved_at: string | null }[]
  approved_submissions: number
}

const SCOPE_COLORS: Record<string, string> = { 'Scope 1': '#059669', 'Scope 2': '#0284c7', 'Scope 3': '#7c3aed' }

export default function Consolidated() {
  const { t } = useI18n()
  const [year, setYear] = useState('all')
  const [c, setC] = useState<Consol | null>(null)

  useEffect(() => {
    api.get('/submissions/consolidated', { params: year !== 'all' ? { year: Number(year) } : {} }).then((r) => setC(r.data))
  }, [year])

  if (!c) return <Spinner label={t('loading')} />
  const scopes = Object.entries(c.by_scope_kg).map(([k, v]) => ({ name: k, kg: Number(v) }))
  const monthly = Object.entries(c.monthly_kg).map(([k, v]) => ({ month: k, t: Number(v) / 1000 }))
  const years = ['all', ...Array.from({ length: 7 }, (_, i) => String(new Date().getFullYear() - i))]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="me-auto text-xl font-bold text-slate-800">{t('consolidatedReport')}</h1>
        <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-600/20">
          {t('approvedOnly')} ({c.approved_submissions})
        </span>
        <Select value={year} onChange={setYear} className="w-32"
          options={years.map((y) => ({ value: y, label: y === 'all' ? t('all') : y }))} />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label={t('totalEmissions')} value={`${fmtKg(c.total_t_co2e, 2)} ${t('tCO2e')}`} sub={`${fmtKg(c.total_kg_co2e)} kg`} />
        <StatCard label={t('approved')} value={String(c.approved_submissions)} accent="sky" />
        <StatCard label={t('facilities')} value={String(c.facilities.length)} accent="sky" />
        <StatCard label={t('scope1')} value={`${fmtKg(Number(c.by_scope_kg['Scope 1'] ?? 0) / 1000, 1)} ${t('tCO2e')}`} accent="brand" />
      </div>

      {c.approved_submissions === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
          {t('noData')} — {t('approvedOnly')}
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title={`${t('monthlyEmissions')} (${t('tCO2e')})`} className="lg:col-span-2">
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={monthly} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="month" fontSize={11} />
                <YAxis fontSize={11} />
                <Tooltip formatter={(v: number) => `${v.toLocaleString()} t`} />
                <Line type="monotone" dataKey="t" stroke="#047857" strokeWidth={2.5} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </Card>
          <Card title={t('facilityComparison')}>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={c.facilities} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="facility_name" fontSize={11} />
                <YAxis fontSize={11} />
                <Tooltip formatter={(v: number) => `${v.toLocaleString()} kg`} />
                <Bar dataKey="total_kg_co2e" name="kg CO₂e" fill="#059669" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card title={t('byScope')}>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={scopes} dataKey="kg" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={2}>
                  {scopes.map((e) => <Cell key={e.name} fill={SCOPE_COLORS[e.name] ?? '#94a3b8'} />)}
                </Pie>
                <Legend iconSize={10} formatter={(v) => <span className="text-xs text-slate-600">{v}</span>} />
                <Tooltip formatter={(v: number) => `${v.toLocaleString()} kg`} />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </div>
      )}

      {c.facilities.length > 0 && (
        <Card title={t('facilities')}>
          <table className="min-w-full divide-y divide-slate-100 text-sm">
            <thead className="text-xs text-slate-500">
              <tr>{[t('facility'), t('total'), t('approved'), t('reviewedBy')].map((h) => <th key={h} className="px-3 py-2 text-start">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {c.facilities.map((f) => (
                <tr key={f.facility_id}>
                  <td className="px-3 py-2 font-medium">{f.facility_name}</td>
                  <td className="px-3 py-2 tabular-nums">{fmtKg(f.total_kg_co2e)} kg ({(Number(f.total_kg_co2e) / 1000).toFixed(2)} t)</td>
                  <td className="px-3 py-2">{f.submissions}</td>
                  <td className="px-3 py-2 text-xs text-slate-400">{f.last_approved_at?.slice(0, 10) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
