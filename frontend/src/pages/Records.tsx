import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errMsg } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Badge, Button, DataTable, Input, Modal, Select, StatusBadge, Textarea } from '../components/ui'
import { useI18n } from '../i18n'

type Row = Record<string, any>

const SCOPES = ['Scope 1', 'Scope 2', 'Scope 3']

export default function Records() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [meta, setMeta] = useState<any>(null)
  const [facilities, setFacilities] = useState<any[]>([])
  const [filters, setFilters] = useState({ search: '', year: 'all', scope: 'all', status: 'all', category: 'all', facility: 'all' })
  const [detail, setDetail] = useState<Row | null>(null)
  const [ov, setOv] = useState<{ scope: string; sub: string; reason: string } | null>(null)
  const [msg, setMsg] = useState('')

  const canWrite = user?.role !== 'viewer'
  const isStaff = user?.role === 'admin' || user?.role === 'head_office'

  const load = useCallback(() => {
    const params: Record<string, any> = { page, page_size: 25 }
    if (filters.search) params.search = filters.search
    if (filters.year !== 'all') params.year = filters.year
    if (filters.scope !== 'all') params.scope = filters.scope
    if (filters.status !== 'all') params.calc_status = filters.status
    if (filters.category !== 'all') params.category_key = filters.category
    if (filters.facility !== 'all') params.facility_id = filters.facility
    api.get('/records', { params }).then((r) => { setRows(r.data.rows); setTotal(r.data.total) })
  }, [page, filters])

  useEffect(load, [load])
  useEffect(() => { api.get('/records/meta').then((r) => setMeta(r.data)) }, [])
  useEffect(() => {
    if (isStaff) api.get('/org/facilities').then((r) => setFacilities(r.data))
  }, [isStaff])

  const saveOverride = async () => {
    if (!detail || !ov) return
    try {
      await api.post(`/records/${detail.record_id}/scope-override`, {
        scope: ov.scope, subcategory: ov.sub || null, reason: ov.reason,
      })
      setOv(null); setDetail(null); setMsg(''); load()
    } catch (e) { setMsg(errMsg(e)) }
  }

  const years = ['all', ...Array.from({ length: 7 }, (_, i) => String(new Date().getFullYear() - i))]

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="me-auto text-xl font-bold text-slate-800">{t('navRecords')}</h1>
        {canWrite && <Link to="/records/new"><Button>{t('navNewRecord')} +</Button></Link>}
      </div>

      <div className="flex flex-wrap gap-3 rounded-xl border border-slate-200 bg-white p-3">
        <Input label={t('search')} value={filters.search} onChange={(v) => { setFilters({ ...filters, search: v }); setPage(1) }} className="w-56" />
        <Select label={t('year')} value={filters.year} onChange={(v) => { setFilters({ ...filters, year: v }); setPage(1) }} className="w-28"
          options={years.map((y) => ({ value: y, label: y === 'all' ? t('all') : y }))} />
        <Select label={t('byScope')} value={filters.scope} onChange={(v) => { setFilters({ ...filters, scope: v }); setPage(1) }} className="w-32"
          options={[{ value: 'all', label: t('all') }, ...SCOPES.map((s) => ({ value: s, label: t(s === 'Scope 1' ? 'scope1' : s === 'Scope 2' ? 'scope2' : 'scope3') }))]} />
        <Select label={t('calcStatus')} value={filters.status} onChange={(v) => { setFilters({ ...filters, status: v }); setPage(1) }} className="w-36"
          options={[{ value: 'all', label: t('all') }, ...['calculated', 'needs_review', 'needs_factor', 'needs_date', 'rejected_unit'].map((s) => ({ value: s, label: s }))]} />
        <Select label={t('category')} value={filters.category} onChange={(v) => { setFilters({ ...filters, category: v }); setPage(1) }} className="w-44"
          options={[{ value: 'all', label: t('all') }, ...(meta?.categories ?? []).map((c: any) => ({ value: c.category_key, label: c.category_key }))]} />
        {isStaff && (
          <Select label={t('facility')} value={filters.facility} onChange={(v) => { setFilters({ ...filters, facility: v }); setPage(1) }} className="w-48"
            options={[{ value: 'all', label: t('all') }, ...facilities.map((f: any) => ({ value: String(f.facility_id), label: f.name }))]} />
        )}
      </div>

      <DataTable<Row>
        rows={rows}
        pageSize={25}
        onRowClick={(r) => setDetail(r)}
        columns={[
          { key: 'activity_date', label: t('activityDate'), sortable: true },
          { key: 'activity_name', label: t('activityName'), sortable: true },
          { key: 'facility_name', label: t('facility') },
          { key: 'scope', label: t('byScope'), render: (r) => (r.scope ? <Badge tone={r.scope === 'Scope 1' ? 'green' : r.scope === 'Scope 2' ? 'blue' : 'purple'}>{r.scope}</Badge> : <Badge tone="amber">—</Badge>) },
          { key: 'quantity', label: t('quantity'), render: (r) => `${r.quantity} ${r.unit}` },
          { key: 'kg_co2e', label: t('kgCO2e'), sortable: true, render: (r) => (r.kg_co2e ? Number(r.kg_co2e).toLocaleString() : '—') },
          { key: 'calc_status', label: t('calcStatus'), render: (r) => <StatusBadge status={r.calc_status} /> },
          { key: 'factor_source', label: t('factorSource') },
        ]}
      />
      <div className="text-center text-xs text-slate-400">{total} {t('records')}</div>

      <Modal open={!!detail} title={t('recordDetail')} onClose={() => setDetail(null)} wide>
        {detail && (
          <div className="space-y-3 text-sm">
            {msg && <div className="rounded bg-rose-50 px-3 py-2 text-rose-700">{msg}</div>}
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 md:grid-cols-3">
              {[{ k: t('activityName'), v: detail.activity_name }, { k: t('description'), v: detail.description },
                { k: t('activityDate'), v: detail.activity_date ?? '—' }, { k: t('facility'), v: detail.facility_name },
                { k: t('category'), v: detail.category_key }, { k: t('byScope'), v: detail.scope ?? '—' },
                { k: t('subcategory'), v: detail.scope_subcategory ?? '—' }, { k: t('quantity'), v: `${detail.quantity} ${detail.unit}` },
                { k: t('factor'), v: detail.factor_value ? `${detail.factor_value} ${detail.factor_unit ?? ''}` : '—' },
                { k: t('factorSource'), v: detail.factor_source }, { k: t('factorClass'), v: detail.factor_class },
                { k: t('factorVerification'), v: detail.factor_verification },
                { k: t('kgCO2e'), v: detail.kg_co2e }, { k: 't CO₂e', v: detail.t_co2e },
                { k: t('calcStatus'), v: detail.calc_status }, { k: t('notes'), v: detail.calc_notes },
              ].map(({ k, v }) => (
                <div key={k as string}>
                  <div className="text-xs text-slate-400">{k}</div>
                  <div className="text-slate-800">{String(v ?? '—')}</div>
                </div>
              ))}
            </div>
            <div className="rounded bg-slate-50 p-2 text-xs text-slate-500">{detail.scope_reason}</div>
            {canWrite && (
              <Button variant="outline" onClick={() => setOv({ scope: detail.scope ?? 'Scope 1', sub: detail.scope_subcategory ?? '', reason: '' })}>
                {t('overrideScopeTitle')}
              </Button>
            )}
          </div>
        )}
      </Modal>

      <Modal open={!!ov} title={t('overrideScopeTitle')} onClose={() => setOv(null)}>
        {ov && (
          <div className="space-y-3">
            <Select label={t('byScope')} value={ov.scope} onChange={(v) => setOv({ ...ov, scope: v })}
              options={SCOPES.map((s) => ({ value: s, label: s }))} />
            <Input label={t('subcategory')} value={ov.sub} onChange={(v) => setOv({ ...ov, sub: v })} />
            <Textarea label={t('newReasonRequired')} value={ov.reason} onChange={(v) => setOv({ ...ov, reason: v })} rows={2} />
            <Button onClick={saveOverride} disabled={!ov.reason.trim()}>{t('save')}</Button>
          </div>
        )}
      </Modal>
    </div>
  )
}
