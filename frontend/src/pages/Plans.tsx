import { useCallback, useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, errMsg } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import KpiCards from '../components/KpiCards'
import { Badge, Button, Card, DataTable, Input, Modal, Select, StatusBadge, Textarea } from '../components/ui'
import { useI18n } from '../i18n'

const AREAS = ['رفع كفاءة الكهرباء', 'تحسين كفاءة الوقود', 'تحسين النقل والشحن', 'تقليل المخلفات',
  'تحسين كفاءة المياه', 'مراجعة المشتريات', 'Electricity efficiency', 'Fuel efficiency',
  'Transport & freight', 'Waste reduction', 'Water efficiency', 'Procurement review']
const EMPTY = {
  area: AREAS[0], description: '', owner: '', target_date: '', status: 'planned',
  linked_category_key: '', assumptions: '', target_scope: '', target_facility_id: '',
  activity: '', baseline_kg: '', expected_reduction_pct: '', kpi: '', priority: 'medium',
  reference_source: '', plan_year: '',
}

export default function Plans() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [rows, setRows] = useState<any[]>([])
  const [meta, setMeta] = useState<any>(null)
  const [insights, setInsights] = useState<any>(null)
  const [roadmap, setRoadmap] = useState<any>(null)
  const [summary, setSummary] = useState<any>(null)
  const [facilities, setFacilities] = useState<any[]>([])
  const [form, setForm] = useState({ ...EMPTY } as any)
  const [edit, setEdit] = useState<any | null>(null)
  const [target, setTarget] = useState({ baseline_year: String(new Date().getFullYear()), target_year: String(new Date().getFullYear() + 1), reduction_pct: '10', note: '' })
  const [msg, setMsg] = useState('')
  const [filters, setFilters] = useState({ facility: 'all', year: 'all', scope: 'all', from: '', to: '' })
  const [results, setResults] = useState<any>(null)
  const [resultsFor, setResultsFor] = useState<any>(null)
  const [overview, setOverview] = useState<any>(null)

  const isStaff = user?.role === 'admin' || user?.role === 'head_office'

  const load = useCallback(() => {
    const p: any = {}
    if (filters.facility !== 'all') p.facility_id = filters.facility
    if (filters.year !== 'all') p.year = filters.year
    if (filters.scope !== 'all') p.scope = filters.scope
    if (filters.from) p.date_from = filters.from
    if (filters.to) p.date_to = filters.to
    api.get('/plans').then((r) => setRows(r.data))
    api.get('/plans/insights', { params: p }).then((r) => setInsights(r.data)).catch(() => {})
    api.get('/plans/roadmap', { params: p }).then((r) => setRoadmap(r.data)).catch(() => {})
    api.get('/dashboard/summary', { params: p }).then((r) => setSummary(r.data)).catch(() => setSummary(null))
    api.get('/plans/results-overview', { params: p }).then((r) => setOverview(r.data)).catch(() => setOverview(null))
  }, [filters])
  useEffect(load, [load])
  useEffect(() => {
    api.get('/records/meta').then((r) => setMeta(r.data))
    if (isStaff) api.get('/org/facilities').then((r) => setFacilities(r.data)).catch(() => {})
  }, [isStaff])

  const save = async () => {
    setMsg('')
    try {
      const body: any = {
        ...form,
        expected_reduction_pct: form.expected_reduction_pct === '' ? null : Number(form.expected_reduction_pct),
        plan_year: form.plan_year === '' ? null : Number(form.plan_year),
        target_facility_id: form.target_facility_id === '' ? null : Number(form.target_facility_id),
        target_date: form.target_date || null, linked_category_key: form.linked_category_key || null,
        target_scope: form.target_scope || null, activity: form.activity || null,
        baseline_kg: form.baseline_kg === '' ? null : String(form.baseline_kg),
        reference_source: form.reference_source || null, kpi: form.kpi || null,
      }
      if (edit) await api.patch(`/plans/${edit.plan_id}`, body)
      else await api.post('/plans', body)
      setForm({ ...EMPTY }); setEdit(null); load()
    } catch (e) { setMsg(errMsg(e)) }
  }

  const addTarget = async () => {
    setMsg('')
    try {
      await api.post('/plans/targets', {
        baseline_year: Number(target.baseline_year), target_year: Number(target.target_year),
        reduction_pct: target.reduction_pct === '' ? null : Number(target.reduction_pct),
        note: target.note,
      })
      load()
    } catch (e) { setMsg(errMsg(e)) }
  }

  const showResults = async (plan: any) => {
    setMsg(''); setResultsFor(plan); setResults(null)
    try {
      const r = await api.get(`/plans/${plan.plan_id}/results`)
      setResults(r.data)
    } catch (e) { setMsg(errMsg(e)); setResultsFor(null) }
  }

  const canWrite = user?.role !== 'viewer'
  const roadmapData = (roadmap?.years ?? []).map((r: any) => ({
    year: String(r.year), actual: r.actual_kg ? Number(r.actual_kg) : null, target: r.target_kg ? Number(r.target_kg) : null,
  }))
  const monthly = Object.entries(summary?.monthly_kg ?? {})
    .map(([m, v]) => ({ month: m, kg: Number(v) }))
    .sort((a, b) => a.month.localeCompare(b.month))
  const months = monthly.map((m, i) => {
    const prev = i > 0 ? monthly[i - 1].kg : null
    const delta = prev && prev > 0 ? Math.round((m.kg - prev) / prev * 1000) / 10 : null
    return { ...m, delta }
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="me-auto text-xl font-bold text-slate-800">{t('navPlans')}</h1>
        {isStaff && (
          <Select label={t('facility')} value={filters.facility} onChange={(v) => setFilters({ ...filters, facility: v })} className="w-48"
            options={[{ value: 'all', label: t('all') }, ...facilities.map((f: any) => ({ value: String(f.facility_id), label: f.name }))]} />
        )}
        <Select label={t('year')} value={filters.year} onChange={(v) => setFilters({ ...filters, year: v })} className="w-28"
          options={['all', ...Array.from({ length: 7 }, (_, i) => String(new Date().getFullYear() - i))].map((y) => ({ value: y, label: y === 'all' ? t('all') : y }))} />
        <Select label={t('byScope')} value={filters.scope} onChange={(v) => setFilters({ ...filters, scope: v })} className="w-32"
          options={[{ value: 'all', label: t('all') }, ...['Scope 1', 'Scope 2', 'Scope 3'].map((s) => ({ value: s, label: s }))]} />
        <Input label={t('from')} type="date" value={filters.from} onChange={(v) => setFilters({ ...filters, from: v })} className="w-36" />
        <Input label={t('to')} type="date" value={filters.to} onChange={(v) => setFilters({ ...filters, to: v })} className="w-36" />
      </div>
      {msg && <div className="rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-700">{msg}</div>}

      {summary && <KpiCards s={summary} />}

      {months.length > 0 && (
        <Card title={`${t('monthlyChanges')} (${t('comparedToPrev')})`}>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {months.slice(-8).map((m) => (
              <div key={m.month} className="rounded-lg border border-slate-200 p-2 text-sm">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>{m.month}</span>
                  {m.delta == null ? <span>—</span> : (
                    <span className={m.delta > 0 ? 'text-rose-600' : 'text-emerald-600'}>
                      {m.delta > 0 ? '↑' : '↓'} {Math.abs(m.delta)}%
                    </span>
                  )}
                </div>
                <div className="font-bold tabular-nums">{m.kg.toLocaleString()} kg</div>
              </div>
            ))}
          </div>
          {months.length < 2 && <p className="mt-2 text-xs text-slate-400">{t('noDataMonth')}</p>}
        </Card>
      )}

      {months.length > 0 && (
        <Card title={t('monthlyEmissions')}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={months} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="month" fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip formatter={(v: number) => `${v.toLocaleString()} kg`} />
              <Bar dataKey="kg" fill="#059669" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {overview && (
        <Card title={t('planOverall')}>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-slate-400">{t('overallMeasured')}</div>
              <div className="text-xl font-bold tabular-nums">{overview.overall_measured_reduction_pct ?? '—'}%</div>
              <div className="text-[11px] text-slate-400">{Number(overview.overall_baseline_kg).toLocaleString()} → {Number(overview.overall_actual_kg).toLocaleString()} kg</div>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-slate-400">{t('overallTargetPct')}</div>
              <div className="text-xl font-bold tabular-nums">{overview.overall_target_reduction_pct ?? '—'}%</div>
              <div className="text-[11px] text-slate-400">{t('computedTargetNote')}</div>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-slate-400">{t('plans')}</div>
              <div className="text-xl font-bold tabular-nums">{overview.plans_evaluated} ({overview.with_baseline} {t('withBaselineShort')})</div>
            </div>
          </div>
          <p className="mt-2 text-[11px] text-slate-400">{overview.overall_target_basis}</p>
        </Card>
      )}

      {insights && (
        <Card title={t('insights')}>
          <div className="space-y-2">
            {insights.suggestions?.map((s: any, i: number) => (
              <div key={i} className="rounded-lg border border-slate-200 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <b className="text-sm">{s.area}</b>
                  <Badge tone={s.priority === 'high' ? 'red' : 'amber'}>{s.priority}</Badge>
                  <Badge tone="gray">{s.category_key}</Badge>
                  <span className="text-xs text-slate-500">{t('baseline')}: {Number(s.baseline_kg).toLocaleString()} kg</span>
                  <Button variant="outline" className="ms-auto !px-2 !py-1 text-xs" onClick={() => setForm({
                    ...EMPTY, area: s.area, linked_category_key: s.category_key, baseline_kg: s.baseline_kg,
                    priority: s.priority, reference_source: s.reference, description: s.methodology,
                  })}>{t('useSuggestion')}</Button>
                </div>
                <div className="mt-1 text-xs text-slate-500">{s.rationale}</div>
                <div className="text-xs text-slate-400">📚 {s.reference}</div>
                <div className="text-xs text-slate-400">{s.methodology}</div>
              </div>
            ))}
            {!insights.suggestions?.length && <p className="text-xs text-slate-400">{t('noData')}</p>}
          </div>
          <p className="mt-2 text-[11px] text-slate-400">{insights.disclaimer}</p>
        </Card>
      )}

      {canWrite && (
        <Card title={edit ? `${t('edit')} #${edit.plan_id}` : t('newPlan')}>
          <div className="grid gap-3 md:grid-cols-3">
            <Select label={t('area')} value={form.area} onChange={(v) => setForm({ ...form, area: v })}
              options={AREAS.map((a) => ({ value: a, label: a }))} />
            <Input label={t('owner')} value={form.owner} onChange={(v) => setForm({ ...form, owner: v })} />
            <Input label={t('targetDate')} type="date" value={form.target_date} onChange={(v) => setForm({ ...form, target_date: v })} />
            <Select label={t('status')} value={form.status} onChange={(v) => setForm({ ...form, status: v })}
              options={['planned', 'in_progress', 'done', 'cancelled'].map((s) => ({ value: s, label: t(s as any) }))} />
            <Select label={t('priority')} value={form.priority} onChange={(v) => setForm({ ...form, priority: v })}
              options={['high', 'medium', 'low'].map((p) => ({ value: p, label: p }))} />
            <Select label={`${t('category')} (${t('optional')})`} value={form.linked_category_key} onChange={(v) => setForm({ ...form, linked_category_key: v })}
              options={[{ value: '', label: '—' }, ...(meta?.categories ?? []).map((c: any) => ({ value: c.category_key, label: c.category_key }))]} />
            <Input label={t('baseline') + ' (kg)'} type="number" step="any" value={form.baseline_kg} onChange={(v) => setForm({ ...form, baseline_kg: v })} />
            <Input label={t('expectedReduction')} type="number" step="any" value={form.expected_reduction_pct} onChange={(v) => setForm({ ...form, expected_reduction_pct: v })} />
            <Input label={t('kpi')} value={form.kpi} onChange={(v) => setForm({ ...form, kpi: v })} />
            <Input label={t('referenceSource')} value={form.reference_source} onChange={(v) => setForm({ ...form, reference_source: v })} className="md:col-span-2" />
            <Input label={t('planYear')} type="number" value={form.plan_year} onChange={(v) => setForm({ ...form, plan_year: v })} />
          </div>
          <Textarea label={t('description')} value={form.description} onChange={(v) => setForm({ ...form, description: v })} rows={2} className="mt-3" />
          <Textarea label={t('assumptions')} value={form.assumptions} onChange={(v) => setForm({ ...form, assumptions: v })} rows={2} className="mt-3" />
          <div className="mt-2 flex gap-2">
            <Button onClick={save} disabled={!form.area}>{edit ? t('save') : t('create')}</Button>
            {edit && <Button variant="ghost" onClick={() => { setEdit(null); setForm({ ...EMPTY }) }}>{t('cancel')}</Button>}
          </div>
          <p className="mt-1 text-[11px] text-slate-400">
            لا تُقبل نسبة خفض متوقعة دون مصدر مرجعي ومؤشر متابعة. Decrease percentages require a reference source and a KPI.
          </p>
        </Card>
      )}

      {isStaff && (
        <Card title={t('addTarget')}>
          <div className="flex flex-wrap items-end gap-3">
            <Input label={t('baseline')} type="number" value={target.baseline_year} onChange={(v) => setTarget({ ...target, baseline_year: v })} className="w-28" />
            <Input label={t('targetYear')} type="number" value={target.target_year} onChange={(v) => setTarget({ ...target, target_year: v })} className="w-28" />
            <Input label={t('targetReductionPct')} type="number" step="any" value={target.reduction_pct} onChange={(v) => setTarget({ ...target, reduction_pct: v })} className="w-40" />
            <Input label={t('notes')} value={target.note} onChange={(v) => setTarget({ ...target, note: v })} className="w-64" />
            <Button onClick={addTarget}>{t('addTarget')}</Button>
          </div>
        </Card>
      )}

      {roadmapData.length > 0 && (
        <Card title={t('roadmap')}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={roadmapData} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="year" fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip formatter={(v: number) => `${v?.toLocaleString?.() ?? v} kg`} />
              <Legend iconSize={10} formatter={(v) => <span className="text-xs">{v}</span>} />
              <Bar dataKey="actual" name={t('actual')} fill="#059669" radius={[4, 4, 0, 0]} />
              <Bar dataKey="target" name={t('target')} fill="#f59e0b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      <DataTable rows={rows} columns={[
        { key: 'plan_id', label: '#', sortable: true },
        { key: 'area', label: t('area') },
        { key: 'description', label: t('description') },
        { key: 'priority', label: t('priority') },
        { key: 'owner', label: t('owner') },
        { key: 'target_date', label: t('targetDate') },
        { key: 'status', label: t('status'), render: (r) => <StatusBadge status={r.status} /> },
        { key: 'baseline_kg', label: t('baseline'), render: (r) => r.baseline_kg ? `${Number(r.baseline_kg).toLocaleString()} kg` : '—' },
        { key: 'expected_reduction_pct', label: '%', render: (r) => r.expected_reduction_pct != null ? `${r.expected_reduction_pct}%` : '—' },
        { key: 'results', label: t('planResults'), render: (r: any) => (
          <Button variant="outline" className="!px-2 !py-1 text-xs" onClick={() => showResults(r)}>📊</Button>
        ) },
        ...(canWrite ? [{
          key: 'act', label: t('actions'), render: (r: any) => (
            <Button variant="outline" className="!px-2 !py-1 text-xs" onClick={() => {
              setEdit(r)
              setForm({
                area: r.area, description: r.description ?? '', owner: r.owner ?? '', target_date: r.target_date ?? '',
                status: r.status, linked_category_key: r.linked_category_key ?? '', assumptions: r.assumptions ?? '',
                target_scope: r.target_scope ?? '', target_facility_id: r.target_facility_id ?? '', activity: r.activity ?? '',
                baseline_kg: r.baseline_kg ?? '', expected_reduction_pct: r.expected_reduction_pct ?? '',
                kpi: r.kpi ?? '', priority: r.priority ?? 'medium', reference_source: r.reference_source ?? '',
                plan_year: r.plan_year ?? '',
              })
              window.scrollTo({ top: 0, behavior: 'smooth' })
            }}>{t('edit')}</Button>
          )
        } as any] : []),
      ]} />
      <p className="text-[11px] text-slate-400">
        توصيات المخططات مبنية على الانبعاثات المحسوبة فعليًا ولا تعني خفضًا مضمونًا.
        Projected reductions are not guaranteed; every figure requires a documented site-specific basis.
      </p>

      <Modal open={!!resultsFor} title={`${t('planResults')} — ${resultsFor?.area ?? ''}`} onClose={() => { setResultsFor(null); setResults(null) }}>
        {results && (
          <div className="space-y-2 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded bg-slate-50 p-2"><div className="text-xs text-slate-400">{t('baseline')}</div><b>{results.baseline_kg ? `${Number(results.baseline_kg).toLocaleString()} kg` : '—'}</b></div>
              <div className="rounded bg-slate-50 p-2"><div className="text-xs text-slate-400">{t('actualKg')}</div><b>{Number(results.actual_kg).toLocaleString()} kg</b></div>
              <div className="rounded bg-slate-50 p-2"><div className="text-xs text-slate-400">{t('savings')}</div><b>{results.savings_kg ? `${Number(results.savings_kg).toLocaleString()} kg` : '—'}</b></div>
              <div className="rounded bg-slate-50 p-2"><div className="text-xs text-slate-400">{t('reductionPct')}</div><b>{results.reduction_pct ?? '—'}%</b></div>
            </div>
            <div className="text-xs text-slate-500">{t('baselineSource')}: {results.baseline_source}</div>
            <div className="flex items-center gap-2 text-xs">
              <StatusBadge status={results.status === 'achieved' ? 'approved' : results.status === 'partial' ? 'submitted' : results.status === 'not_achieved' ? 'rejected' : 'withdrawn'} />
              <span>{t('targetPct')}: {results.target_reduction_pct ?? '—'}%</span>
            </div>
            <p className="text-[11px] text-slate-400">{results.note}</p>
          </div>
        )}
      </Modal>
    </div>
  )
}
