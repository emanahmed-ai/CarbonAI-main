import { useCallback, useEffect, useState } from 'react'
import { api, errMsg } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Badge, Button, Card, DataTable, Input, Modal, Select, StatusBadge, Textarea } from '../components/ui'
import { useI18n } from '../i18n'

type Invoice = Record<string, any>

const CATS = ['electricity', 'stationary_fuel', 'mobile_fuel', 'refrigerant', 'water', 'waste',
  'process_emissions', 'transport_freight', 'business_travel', 'purchased_goods', 'other']
const UNITS = ['kWh', 'MWh', 'GJ', 'MJ', 'litre', 'm3', 'kg', 'tonne', 'km', 'tkm', 'pkm', 'unit']

export default function Invoices() {
  const { t } = useI18n()
  const { user } = useAuth()
  const isStaff = user?.role === 'admin' || user?.role === 'head_office'
  const [rows, setRows] = useState<Invoice[]>([])
  const [facilities, setFacilities] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [detail, setDetail] = useState<Invoice | null>(null)
  const [calc, setCalc] = useState<Invoice | null>(null)
  const [calcForm, setCalcForm] = useState({ ownership_control: 'unknown', energy_purchased: 'unknown', value_chain_relation: 'unknown' })
  const [voidForm, setVoidForm] = useState<{ inv: Invoice; reason: string } | null>(null)
  const [fileUrl, setFileUrl] = useState<string | null>(null)
  const [form, setForm] = useState({
    facility_id: '', invoice_name: '', invoice_number: '', supplier: '', invoice_date: '',
    category_key: 'electricity', quantity: '', unit: 'kWh', amount: '', notes: '',
  })
  const [file, setFile] = useState<File | null>(null)
  const [filters, setFilters] = useState({ search: '', year: 'all', month: 'all', status: 'all' })

  const load = useCallback(() => {
    const p: any = {}
    if (filters.search) p.search = filters.search
    if (filters.year !== 'all') p.year = filters.year
    if (filters.month !== 'all') p.month = filters.month
    if (filters.status !== 'all') p.status = filters.status
    api.get('/invoices', { params: p }).then((r) => setRows(r.data))
  }, [filters])
  useEffect(load, [load])
  useEffect(() => { if (isStaff) api.get('/org/facilities').then((r) => setFacilities(r.data)) }, [isStaff])

  const create = async () => {
    setMsg(''); setBusy(true)
    try {
      const fd = new FormData()
      const payload: any = { ...form }
      if (payload.facility_id) payload.facility_id = Number(payload.facility_id)
      if (payload.invoice_date) {
        payload.period_year = Number(payload.invoice_date.slice(0, 4))
        payload.period_month = Number(payload.invoice_date.slice(5, 7))
      }
      for (const [k, v] of Object.entries(payload)) if (v !== '' && v != null) fd.append(k, String(v))
      if (file) fd.append('file', file)
      await api.post('/invoices', fd)
      setForm({ ...form, invoice_name: '', invoice_number: '', supplier: '', invoice_date: '', quantity: '', amount: '', notes: '' })
      setFile(null); load()
    } catch (e: any) {
      if (e?.response?.status === 409) setMsg(`${t('duplicateInvoice')}: ${e.response.data?.detail?.detail ?? ''}`)
      else setMsg(errMsg(e))
    } finally { setBusy(false) }
  }

  const openDetail = async (r: Invoice) => {
    setDetail(r)
    setFileUrl(null)
    try {
      const d = await api.get(`/invoices/${r.invoice_id}`)
      setDetail(d.data)
      if (d.data.file_path) {
        const blob = await api.get(`/invoices/${r.invoice_id}/file`, { responseType: 'blob' })
        setFileUrl(URL.createObjectURL(blob.data))
      }
    } catch (e) { setMsg(errMsg(e)) }
  }

  const doCalculate = async () => {
    if (!calc) return
    setMsg(''); setBusy(true)
    try {
      const r = await api.post(`/invoices/${calc.invoice_id}/calculate`, { ...calcForm })
      setCalc(null)
      const f = r.data.factor
      setMsg(`✓ ${r.data.kg_co2e} kg CO₂e — ${f.factor_id} v${f.version} (${f.value} ${f.unit}) · ${f.source} · ${f.status}`)
      load()
    } catch (e) { setMsg(errMsg(e)) } finally { setBusy(false) }
  }

  const doVoid = async () => {
    if (!voidForm) return
    try {
      await api.post(`/invoices/${voidForm.inv.invoice_id}/void`, { reason: voidForm.reason })
      setVoidForm(null); setDetail(null); load()
    } catch (e) { setMsg(errMsg(e)) }
  }

  const years = ['all', ...Array.from({ length: 7 }, (_, i) => String(new Date().getFullYear() - i))]

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-slate-800">{t('navInvoices')}</h1>
      {msg && <div className="rounded-lg bg-brand-50 px-4 py-2 text-sm text-brand-800 ring-1 ring-inset ring-brand-600/20">{msg}</div>}

      <Card title={t('newInvoice')}>
        <div className="grid gap-3 md:grid-cols-3">
          {isStaff && (
            <Select label={t('facility')} value={form.facility_id} onChange={(v) => setForm({ ...form, facility_id: v })}
              options={[{ value: '', label: '—' }, ...facilities.map((f: any) => ({ value: String(f.facility_id), label: f.name }))]} />
          )}
          <Input label={t('invoiceName')} value={form.invoice_name} onChange={(v) => setForm({ ...form, invoice_name: v })} />
          <Input label={t('invoiceNumber')} value={form.invoice_number} onChange={(v) => setForm({ ...form, invoice_number: v })} />
          <Input label={t('supplier')} value={form.supplier} onChange={(v) => setForm({ ...form, supplier: v })} />
          <Input label={t('invoiceDate')} type="date" value={form.invoice_date} onChange={(v) => setForm({ ...form, invoice_date: v })} />
          <Select label={t('category')} value={form.category_key} onChange={(v) => setForm({ ...form, category_key: v })}
            options={CATS.map((c) => ({ value: c, label: c }))} />
          <Input label={t('quantity')} type="number" step="any" value={form.quantity} onChange={(v) => setForm({ ...form, quantity: v })} />
          <Select label={t('unit')} value={form.unit} onChange={(v) => setForm({ ...form, unit: v })}
            options={UNITS.map((u) => ({ value: u, label: u }))} />
          <Input label={t('amount')} type="number" step="any" value={form.amount} onChange={(v) => setForm({ ...form, amount: v })} />
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">{t('attachInvoice')} (PDF/JPG/PNG)</span>
            <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="w-full rounded-lg border border-dashed border-slate-300 px-3 py-1.5 text-xs file:mr-2 file:rounded file:border-0 file:bg-brand-50 file:px-2 file:text-brand-700" />
          </label>
          <Textarea label={t('notes')} value={form.notes} onChange={(v) => setForm({ ...form, notes: v })} rows={1} className="md:col-span-2" />
          <div className="flex items-end">
            <Button onClick={create} disabled={busy || !form.invoice_name || (!isStaff && !user?.facility_id) || (isStaff && !form.facility_id)}>
              {busy ? '…' : `💾 ${t('save')}`}
            </Button>
          </div>
        </div>
      </Card>

      <div className="flex flex-wrap gap-3 rounded-xl border border-slate-200 bg-white p-3">
        <Input label={t('search')} value={filters.search} onChange={(v) => setFilters({ ...filters, search: v })} className="w-56" />
        <Select label={t('year')} value={filters.year} onChange={(v) => setFilters({ ...filters, year: v })} className="w-28"
          options={years.map((y) => ({ value: y, label: y === 'all' ? t('all') : y }))} />
        <Select label={t('month')} value={filters.month} onChange={(v) => setFilters({ ...filters, month: v })} className="w-24"
          options={[{ value: 'all', label: t('all') }, ...Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) }))]} />
        <Select label={t('status')} value={filters.status} onChange={(v) => setFilters({ ...filters, status: v })} className="w-36"
          options={[{ value: 'all', label: t('all') }, ...['draft', 'calculated', 'needs_review', 'void'].map((s) => ({ value: s, label: s }))]} />
      </div>

      <DataTable<Invoice> rows={rows} pageSize={15} onRowClick={openDetail} columns={[
        { key: 'invoice_id', label: '#', sortable: true },
        { key: 'invoice_name', label: t('invoiceName') },
        { key: 'invoice_number', label: t('invoiceNumber') },
        { key: 'supplier', label: t('supplier') },
        { key: 'invoice_date', label: t('invoiceDate'), sortable: true },
        { key: 'facility_name', label: t('facility') },
        { key: 'kg_co2e', label: t('kgCO2e'), render: (r) => r.kg_co2e ? Number(r.kg_co2e).toLocaleString() : '—' },
        { key: 'status', label: t('status'), render: (r) => <StatusBadge status={r.status} /> },
        { key: 'file_name', label: t('document'), render: (r) => r.file_name ? <Badge tone="blue">📎</Badge> : '—' },
      ]} />

      <Modal open={!!detail} title={`${t('invoice')} #${detail?.invoice_id}`} onClose={() => { setDetail(null); if (fileUrl) URL.revokeObjectURL(fileUrl); setFileUrl(null) }} wide>
        {detail && (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">
              <StatusBadge status={detail.status} />
              {detail.scope && <Badge tone="green">{detail.scope}</Badge>}
              {detail.kg_co2e && <Badge tone="blue">{Number(detail.kg_co2e).toLocaleString()} kg CO₂e</Badge>}
              {detail.extraction_status !== 'none' && <Badge tone="purple">{t('extraction')}: {detail.extraction_status}</Badge>}
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {[['invoice_name', detail.invoice_name], ['invoice_number', detail.invoice_number],
                ['supplier', detail.supplier], ['invoice_date', detail.invoice_date],
                ['category_key', detail.category_key], ['quantity', `${detail.quantity ?? '—'} ${detail.unit ?? ''}`],
                ['amount', detail.amount ? `${detail.amount} ${detail.currency}` : '—'], ['facility', detail.facility_name],
              ].map(([k, v]) => (
                <div key={String(k)}><div className="text-xs text-slate-400">{String(k)}</div><div>{String(v ?? '—')}</div></div>
              ))}
            </div>
            {detail.extraction_json && detail.extraction_status === 'text_extracted' && (
              <div className="rounded bg-violet-50 p-2 text-xs text-violet-800">
                {t('extractionNote')}
                <pre className="mt-1 overflow-x-auto text-[11px]">{String(detail.extraction_json).slice(0, 600)}</pre>
              </div>
            )}
            {fileUrl && (
              <div className="max-h-64 overflow-auto rounded border border-slate-200">
                {String(detail.file_mime).startsWith('image/') ? (
                  <img src={fileUrl} alt="invoice" className="max-w-full" />
                ) : (
                  <iframe src={fileUrl} title="invoice" className="h-64 w-full" />
                )}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              {detail.status !== 'void' && !detail.record_id && (
                <Button onClick={() => { setCalc(detail); setCalcForm({ ownership_control: 'unknown', energy_purchased: 'unknown', value_chain_relation: 'unknown' }) }}>
                  🧮 {t('calculate')}
                </Button>
              )}
              {isStaff && detail.status !== 'void' && (
                <Button variant="danger" onClick={() => setVoidForm({ inv: detail, reason: '' })}>{t('void')}</Button>
              )}
            </div>
            {detail.audit?.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-medium text-slate-500">{t('auditLog')}</div>
                <ul className="space-y-1 text-xs text-slate-500">
                  {detail.audit.map((a: any) => <li key={a.id}>• {String(a.at).slice(0, 19)} — {a.action} — {a.by} {a.note ? `— ${a.note}` : ''}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </Modal>

      <Modal open={!!calc} title={`🧮 ${t('calculate')} — ${calc?.invoice_name ?? ''}`} onClose={() => setCalc(null)}>
        {calc && (
          <div className="space-y-3 text-sm">
            <div className="rounded bg-slate-50 p-2 text-xs text-slate-600">
              {calc.quantity} {calc.unit} · {calc.category_key} · {calc.invoice_date}
            </div>
            <div className="rounded bg-brand-50 px-3 py-2 text-xs text-brand-800">{t('autoFactorNote')}</div>
            <div className="grid grid-cols-3 gap-2">
              <Select label={t('ownershipControl')} value={calcForm.ownership_control}
                onChange={(v) => setCalcForm({ ...calcForm, ownership_control: v })}
                options={['unknown', 'owned_controlled', 'leased_controlled', 'leased_not_controlled', 'not_controlled'].map((c) => ({ value: c, label: c }))} />
              <Select label={t('energyPurchased')} value={calcForm.energy_purchased}
                onChange={(v) => setCalcForm({ ...calcForm, energy_purchased: v })}
                options={['unknown', 'yes', 'no'].map((c) => ({ value: c, label: c }))} />
              <Select label={t('valueChainRelation')} value={calcForm.value_chain_relation}
                onChange={(v) => setCalcForm({ ...calcForm, value_chain_relation: v })}
                options={['unknown', 'own_fleet', 'on_site_controlled', 'third_party_upstream', 'third_party_downstream', 'business_travel', 'employee'].map((c) => ({ value: c, label: c }))} />
            </div>
            <p className="text-xs text-slate-400">{t('autoFactorHint')}</p>
            <Button onClick={doCalculate} disabled={busy}>
              {t('calculate')}
            </Button>
          </div>
        )}
      </Modal>

      <Modal open={!!voidForm} title={t('void')} onClose={() => setVoidForm(null)}>
        {voidForm && (
          <div className="space-y-3">
            <Textarea label={t('reason')} value={voidForm.reason} onChange={(v) => setVoidForm({ ...voidForm, reason: v })} rows={2} />
            <Button variant="danger" onClick={doVoid} disabled={!voidForm.reason.trim()}>{t('void')}</Button>
          </div>
        )}
      </Modal>
    </div>
  )
}
