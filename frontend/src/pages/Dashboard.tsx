import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api, errMsg } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import KpiCards, { type SummaryKpi } from '../components/KpiCards'
import { Button, Card, EmptyState, Input, Select, Spinner, fmtKg } from '../components/ui'
import { useI18n } from '../i18n'

type Summary = SummaryKpi & {
  by_scope_kg: Record<string, string>
  monthly_kg: Record<string, string>
  top_sources: { activity: string; total_kg_co2e: string }[]
  by_facility: { facility_id: number; facility_name: string; total_kg_co2e: string }[]
  by_category: { category_key: string; total_kg_co2e: string }[]
  yearly_totals: Record<string, string>
  refrigerant: { kg: string; share_of_scope1_pct: number | null; records: number; by_equipment: { equipment: string; kg: string }[] }
}
type Meta = { categories: { category_key: string; name_ar: string; name_en: string }[] }

const SCOPE_COLORS: Record<string, string> = {
  'Scope 1': '#059669', 'Scope 2': '#0284c7', 'Scope 3': '#7c3aed', unscoped: '#94a3b8',
}

export default function Dashboard() {
  const { t, lang } = useI18n()
  const { user } = useAuth()
  const [year, setYear] = useState('all')
  const [month, setMonth] = useState('all')
  const [facilityId, setFacilityId] = useState('all')
  const [scope, setScope] = useState('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [s, setS] = useState<Summary | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [facilities, setFacilities] = useState<{ facility_id: number; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const isStaff = user?.role === 'admin' || user?.role === 'head_office'

  useEffect(() => {
    api.get('/records/meta').then((r) => setMeta(r.data)).catch(() => {})
    if (isStaff) api.get('/org/facilities').then((r) => setFacilities(r.data)).catch(() => {})
  }, [isStaff])

  const load = useCallback(() => {
    const params: Record<string, string> = {}
    if (year !== 'all') params.year = year
    if (month !== 'all') params.month = month
    if (facilityId !== 'all') params.facility_id = facilityId
    if (scope !== 'all') params.scope = scope
    if (dateFrom) params.date_from = dateFrom
    if (dateTo) params.date_to = dateTo
    setLoading(true); setError('')
    api.get('/dashboard/summary', { params })
      .then((r) => setS(r.data))
      .catch((e) => { setS(null); setError(errMsg(e)) })
      .finally(() => setLoading(false))
  }, [year, month, facilityId, scope, dateFrom, dateTo])

  useEffect(() => { load() }, [load])

  if (loading && !s) return <Spinner label={t('loading')} />
  if (error) {
    return (
      <div className="space-y-4">
        <Card title={t('loadFailed')}>
          <p className="text-sm text-rose-700">{error}</p>
          <p className="mt-1 text-xs text-slate-400">{t('loadFailedHint')}</p>
          <Button className="mt-3" onClick={load}>↻ {t('retry')}</Button>
        </Card>
      </div>
    )
  }
  if (!s) return <Spinner label={t('loading')} />

  const years = ['all', ...Array.from({ length: 7 }, (_, i) => String(new Date().getFullYear() - i))]
  const monthly = Object.entries(s.monthly_kg).map(([k, v]) => ({ month: k, kg: Number(v) }))
  const scopes = Object.entries(s.by_scope_kg).map(([k, v]) => ({ name: k, key: k, kg: Number(v) }))
  const scopeLabel = (k: string) => k === 'Scope 1' ? t('scope1') : k === 'Scope 2' ? t('scope2') : t('scope3')
  const catName = (k: string) => {
    const c = meta?.categories.find((x) => x.category_key === k)
    if (!c) return k
    return lang === 'ar' ? c.name_ar : c.name_en
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="me-auto text-xl font-bold text-slate-800">{t('navDashboard')}</h1>
        {isStaff && (
          <Select value={facilityId} onChange={setFacilityId} className="w-48" label={t('facility')}
            options={[{ value: 'all', label: t('all') }, ...facilities.map((f) => ({ value: String(f.facility_id), label: f.name }))]} />
        )}
        <Select label={t('year')} value={year} onChange={setYear} className="w-28"
          options={years.map((y) => ({ value: y, label: y === 'all' ? t('all') : y }))} />
        <Select label={t('month')} value={month} onChange={setMonth} className="w-24"
          options={[{ value: 'all', label: t('all') }, ...Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) }))]} />
        <Select label={t('byScope')} value={scope} onChange={setScope} className="w-32"
          options={[{ value: 'all', label: t('all') }, ...['Scope 1', 'Scope 2', 'Scope 3'].map((x) => ({ value: x, label: scopeLabel(x) }))]} />
        <Input label={t('from')} type="date" value={dateFrom} onChange={setDateFrom} className="w-36" />
        <Input label={t('to')} type="date" value={dateTo} onChange={setDateTo} className="w-36" />
      </div>

      {/* main actions — required order: Company Registration, Activity, Users */}
      <div className="flex flex-wrap gap-2">
        {isStaff && (
          <Link to="/organization"><Button variant="outline">🏢 {t('actionCompany')}</Button></Link>
        )}
        {(user?.role === 'admin' || user?.role === 'head_office' || user?.role === 'factory_manager') && (
          <Link to="/records/new"><Button>➕ {t('actionActivity')}</Button></Link>
        )}
        {isStaff && (
          <Link to="/users"><Button variant="outline">👥 {t('actionUsers')}</Button></Link>
        )}
      </div>

      <KpiCards s={s} />

      {s.refrigerant?.records > 0 && (
        <Card title={t('refrigerantKpi')}>
          <div className="flex flex-wrap items-center gap-6">
            <div>
              <div className="text-xs text-slate-400">{t('kgCO2e')}</div>
              <div className="text-2xl font-bold tabular-nums text-teal-700">{fmtKg(s.refrigerant.kg)} kg</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">{t('shareOfScope1')}</div>
              <div className="text-2xl font-bold tabular-nums">{s.refrigerant.share_of_scope1_pct ?? '—'}%</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">{t('records')}</div>
              <div className="text-2xl font-bold tabular-nums">{s.refrigerant.records}</div>
            </div>
          </div>
        </Card>
      )}

      {s.records === 0 ? (
        <EmptyState text={t('noRecordsYet')} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title={t('monthlyEmissions')}>
            <ResponsiveContainer width="100%" height={260}>
              {monthly.length === 1 ? (
                <BarChart data={monthly} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="month" fontSize={11} />
                  <YAxis fontSize={11} />
                  <Tooltip formatter={(v: number) => `${v.toLocaleString()} ${t('kgCO2e')}`} />
                  <Bar dataKey="kg" fill="#059669" radius={[4, 4, 0, 0]} />
                </BarChart>
              ) : (
                <LineChart data={monthly} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="month" fontSize={11} />
                  <YAxis fontSize={11} />
                  <Tooltip formatter={(v: number) => `${v.toLocaleString()} ${t('kgCO2e')}`} />
                  <Line type="monotone" dataKey="kg" stroke="#059669" strokeWidth={2.5} dot={{ r: 3 }} />
                </LineChart>
              )}
            </ResponsiveContainer>
          </Card>
          <Card title={t('byScope')}>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={scopes.map((x) => ({ ...x, name: scopeLabel(x.key) }))} dataKey="kg" nameKey="name"
                  innerRadius={55} outerRadius={95} paddingAngle={2}>
                  {scopes.map((e) => <Cell key={e.key} fill={SCOPE_COLORS[e.key] ?? '#94a3b8'} />)}
                </Pie>
                <Legend iconSize={10} formatter={(v) => <span className="text-xs text-slate-600">{v}</span>} />
                <Tooltip formatter={(v: number) => `${v.toLocaleString()} ${t('kgCO2e')}`} />
              </PieChart>
            </ResponsiveContainer>
          </Card>
          <Card title={t('yearlyTotals')}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={Object.entries(s.yearly_totals).map(([y, v]) => ({ year: y, kg: Number(v) }))}
                margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="year" fontSize={11} />
                <YAxis fontSize={11} />
                <Tooltip formatter={(v: number) => `${v.toLocaleString()} ${t('kgCO2e')}`} />
                <Bar dataKey="kg" fill="#0f766e" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          {s.by_facility.length > 1 && (
            <Card title={t('facilityComparison')}>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={s.by_facility} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="facility_name" fontSize={11} />
                  <YAxis fontSize={11} />
                  <Tooltip formatter={(v: number) => `${v.toLocaleString()} ${t('kgCO2e')}`} />
                  <Bar dataKey="total_kg_co2e" name={t('kgCO2e')} fill="#047857" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          )}
          <Card title={t('byCategory')}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={s.by_category.map((c) => ({ name: catName(c.category_key), kg: Number(c.total_kg_co2e) }))}
                layout="vertical" margin={{ top: 0, right: 10, bottom: 0, left: 30 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" fontSize={11} />
                <YAxis type="category" dataKey="name" fontSize={10} width={110} />
                <Tooltip formatter={(v: number) => `${v.toLocaleString()} ${t('kgCO2e')}`} />
                <Bar dataKey="kg" fill="#0284c7" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card title={t('topSources')}>
            <table className="w-full text-sm">
              <tbody className="divide-y divide-slate-100">
                {s.top_sources.map((r) => (
                  <tr key={r.activity}>
                    <td className="py-2 text-slate-700">{r.activity}</td>
                    <td className="py-2 text-end font-medium tabular-nums text-slate-800">{fmtKg(r.total_kg_co2e)} kg</td>
                  </tr>
                ))}
                {s.top_sources.length === 0 && <tr><td className="py-6 text-center text-slate-400">{t('noData')}</td></tr>}
              </tbody>
            </table>
            <Link to="/records" className="mt-3 inline-block text-xs font-medium text-brand-600 hover:underline">
              {t('navRecords')} →
            </Link>
          </Card>
        </div>
      )}
    </div>
  )
}
