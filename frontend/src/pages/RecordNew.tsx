import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errMsg } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Badge, Button, Card, Input, Select, Spinner, StatusBadge, Textarea } from '../components/ui'
import { useI18n } from '../i18n'

type Suggestion = {
  message: string
  chosen: { factor: any; tier: number; reason: string; needs_proxy_confirmation: boolean } | null
  candidates: any[]
  excluded: { factor_id: string; reason: string }[]
}
type ScopePreview = { scope: string | null; subcategory: string | null; status: string; confidence: string; reason_en: string; reason_ar: string; missing: string[] }

const CONTROLS = ['unknown', 'owned_controlled', 'leased_controlled', 'leased_not_controlled', 'not_controlled']
const RELATIONS = ['unknown', 'own_fleet', 'on_site_controlled', 'third_party_upstream', 'third_party_downstream', 'business_travel', 'employee']

export default function RecordNew() {
  const { t, lang } = useI18n()
  const { user } = useAuth()
  const nav = useNavigate()
  const [meta, setMeta] = useState<any>(null)
  const [facilities, setFacilities] = useState<any[]>([])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [result, setResult] = useState<any>(null)

  const isStaff = user?.role === 'admin' || user?.role === 'head_office'
  const [f, setF] = useState({
    activity_name: '', description: '', activity_date: '', category_key: 'electricity',
    quantity: '', unit: 'kWh', country_code: 'EG', facility_id: '',
    fuel_or_material: '', ownership_control: 'unknown', energy_purchased: 'unknown',
    value_chain_relation: 'unknown', scope2_method: 'location',
    notes: '', evidence_ref: '', allow_duplicate: false,
  })
  const [override, setOverride] = useState({ on: false, scope: 'Scope 1', sub: '', reason: '' })
  const [mode, setMode] = useState<'library' | 'manual'>('library')
  const [sg, setSg] = useState<Suggestion | null>(null)
  const [picked, setPicked] = useState('')
  const [proxy, setProxy] = useState({ confirmed: false, why: '' })
  const [manual, setManual] = useState({ value: '', source: '', url: '' })
  const [scopePreview, setScopePreview] = useState<ScopePreview | null>(null)

  useEffect(() => {
    api.get('/records/meta').then((r) => {
      setMeta(r.data)
      const dc = localStorage.getItem('carbonai.default_country')
      setF((p) => ({ ...p, country_code: dc || p.country_code }))
    })
    if (isStaff) api.get('/org/facilities').then((r) => setFacilities(r.data))
  }, [isStaff])

  useEffect(() => {
    api.post('/records/scope-preview', {
      activity_name: f.activity_name, description: f.description, category_key: f.category_key,
      ownership_control: f.ownership_control, energy_purchased: f.energy_purchased,
      value_chain_relation: f.value_chain_relation, quantity: f.quantity, unit: f.unit,
    }).then((r) => setScopePreview(r.data)).catch(() => setScopePreview(null))
  }, [f.category_key, f.ownership_control, f.energy_purchased, f.value_chain_relation, f.description])

  const suggestFactor = async () => {
    if (!f.activity_date || !f.category_key || !f.unit) return
    setBusy(true)
    try {
      const r = await api.get('/factors/suggest', {
        params: { country: f.country_code, category: f.category_key, year: f.activity_date.slice(0, 4), unit: f.unit, fuel: f.fuel_or_material || undefined },
      })
      setSg(r.data)
      setPicked(r.data.chosen ? `${r.data.chosen.factor.factor_id}` : '')
    } catch (e) { setMsg(errMsg(e)) } finally { setBusy(false) }
  }

  const save = async () => {
    setMsg(''); setBusy(true); setResult(null)
    const body: any = { ...f, facility_id: f.facility_id ? Number(f.facility_id) : user?.facility_id ?? null }
    if (override.on) {
      body.scope_override_scope = override.scope
      body.scope_override_subcategory = override.sub || null
      body.scope_override_reason = override.reason
    }
    if (mode === 'library' && picked) {
      body.factor = { factor_id: picked, proxy_confirmed: proxy.confirmed, proxy_rationale: proxy.why }
    } else if (mode === 'manual') {
      body.manual_factor = { value: manual.value, source: manual.source, url: manual.url || null }
    }
    try {
      const r = await api.post('/records', body)
      setResult(r.data)
      setF((p) => ({ ...p, activity_name: '', description: '', quantity: '', fuel_or_material: '' }))
      setSg(null); setPicked(''); setManual({ value: '', source: '', url: '' })
    } catch (e) { setMsg(errMsg(e)) } finally { setBusy(false) }
  }

  if (!meta) return <Spinner label={t('loading')} />
  const usable = sg?.candidates.filter((c) => c.usable_without_confirmation) ?? []

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-slate-800">{t('navNewRecord')}</h1>
      {msg && <div className="rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-700 ring-1 ring-inset ring-rose-600/20">{msg}</div>}

      <Card title={t('navRecords')}>
        <div className="grid gap-3 md:grid-cols-3">
          <Input label={t('activityName')} value={f.activity_name} onChange={(v) => setF({ ...f, activity_name: v })} required />
          <Input label={t('description')} value={f.description} onChange={(v) => setF({ ...f, description: v })} />
          <Input label={t('activityDate')} type="date" value={f.activity_date} onChange={(v) => setF({ ...f, activity_date: v })} />
          <Select label={t('category')} value={f.category_key} onChange={(v) => setF({ ...f, category_key: v })}
            options={meta.categories.map((c: any) => ({ value: c.category_key, label: lang === 'ar' ? c.name_ar : c.name_en }))} />
          <Input label={t('quantity')} type="number" step="any" value={f.quantity} onChange={(v) => setF({ ...f, quantity: v })} />
          <Select label={t('unit')} value={f.unit} onChange={(v) => setF({ ...f, unit: v })}
            options={meta.units.map((u: string) => ({ value: u, label: u }))} />
          <Select label={t('country')} value={f.country_code} onChange={(v) => setF({ ...f, country_code: v })}
            options={meta.countries.map((c: any) => ({ value: c.iso2_code, label: `${lang === 'ar' ? c.country_name_ar : c.country_name_en} (${c.iso2_code})` }))} />
          <Input label={`${t('fuelMaterial')} (${t('optional')})`} value={f.fuel_or_material} onChange={(v) => setF({ ...f, fuel_or_material: v })} />
          {isStaff ? (
            <Select label={t('facility')} value={f.facility_id} onChange={(v) => setF({ ...f, facility_id: v })}
              options={[{ value: '', label: '—' }, ...facilities.map((x: any) => ({ value: String(x.facility_id), label: x.name }))]} />
          ) : (
            <div><span className="mb-1 block text-xs font-medium text-slate-600">{t('facility')}</span>
              <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-500">#{user?.facility_id}</div></div>
          )}
        </div>
      </Card>

      <Card title={t('scopeSuggestion')}>
        <div className="grid gap-3 md:grid-cols-3">
          <Select label={t('ownershipControl')} value={f.ownership_control} onChange={(v) => setF({ ...f, ownership_control: v })}
            options={CONTROLS.map((c) => ({ value: c, label: c }))} />
          <Select label={t('energyPurchased')} value={f.energy_purchased} onChange={(v) => setF({ ...f, energy_purchased: v })}
            options={['unknown', 'yes', 'no'].map((c) => ({ value: c, label: t(c as any) ?? c }))} />
          <Select label={t('valueChainRelation')} value={f.value_chain_relation} onChange={(v) => setF({ ...f, value_chain_relation: v })}
            options={RELATIONS.map((c) => ({ value: c, label: c }))} />
        </div>
        {scopePreview && (
          <div className={`mt-3 rounded-lg p-3 text-sm ${scopePreview.status === 'suggested' ? 'bg-brand-50 text-brand-800' : 'bg-amber-50 text-amber-800'}`}>
            <div className="flex flex-wrap items-center gap-2">
              <strong>{scopePreview.scope ?? '— needs review'}</strong>
              {scopePreview.subcategory && <Badge tone="gray">{scopePreview.subcategory}</Badge>}
              <StatusBadge status={scopePreview.status} />
              <span className="text-xs opacity-70">{t('confidence')}: {scopePreview.confidence}</span>
            </div>
            <div className="mt-1 text-xs opacity-80">{lang === 'ar' ? scopePreview.reason_ar : scopePreview.reason_en}</div>
            {scopePreview.missing?.length > 0 && (
              <div className="mt-1 text-xs">{t('missingInfo')}: {scopePreview.missing.join(', ')}</div>
            )}
          </div>
        )}
        {scopePreview?.scope === 'Scope 2' && (
          <div className="mt-2">
            <Select label={t('scope2Method')} value={f.scope2_method} onChange={(v) => setF({ ...f, scope2_method: v })}
              options={[{ value: 'location', label: t('location') }, { value: 'market', label: t('market') }]} />
          </div>
        )}
        <label className="mt-3 flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={override.on} onChange={(e) => setOverride({ ...override, on: e.target.checked })} />
          {t('overrideScope')}
        </label>
        {override.on && (
          <div className="mt-2 grid gap-3 md:grid-cols-3">
            <Select label={t('byScope')} value={override.scope} onChange={(v) => setOverride({ ...override, scope: v })}
              options={['Scope 1', 'Scope 2', 'Scope 3'].map((s) => ({ value: s, label: s }))} />
            <Input label={t('subcategory')} value={override.sub} onChange={(v) => setOverride({ ...override, sub: v })} />
            <Input label={t('newReasonRequired')} value={override.reason} onChange={(v) => setOverride({ ...override, reason: v })} />
          </div>
        )}
      </Card>

      <Card title={t('factorSource')}>
        <div className="mb-3 flex gap-2">
          <Button variant={mode === 'library' ? 'primary' : 'outline'} onClick={() => setMode('library')}>{t('fromLibrary')}</Button>
          <Button variant={mode === 'manual' ? 'primary' : 'outline'} onClick={() => setMode('manual')}>{t('manualEntry')}</Button>
        </div>
        {mode === 'library' ? (
          <div className="space-y-3">
            {!f.activity_date && <div className="text-sm text-amber-600">⚠ {t('activityDate')} — {t('required')}</div>}
            <Button variant="outline" onClick={suggestFactor} disabled={!f.activity_date || busy}>{t('suggestFactor')}</Button>
            {sg && (
              <>
                <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">{sg.message}</div>
                {sg.candidates.length > 0 && (
                  <div className="overflow-x-auto rounded-lg border border-slate-200">
                    <table className="min-w-full divide-y divide-slate-200 text-xs">
                      <thead className="bg-slate-50 text-slate-500">
                        <tr>{[t('chooseFactor'), t('factorValue'), t('country'), 'Tier', t('status'), t('reason')].map((h) => <th key={h} className="px-2 py-1.5 text-start">{h}</th>)}</tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {sg.candidates.map((c) => (
                          <tr key={c.factor_id} className={picked === c.factor_id ? 'bg-brand-50' : ''}>
                            <td className="px-2 py-1.5">
                              <label className="flex items-center gap-1">
                                <input type="radio" name="factor" checked={picked === c.factor_id} onChange={() => setPicked(c.factor_id)} />
                                <span className="font-medium">{c.factor_id} v{c.version}</span>
                                {c.activity && <span className="text-slate-400">· {c.activity}</span>}
                              </label>
                            </td>
                            <td className="px-2 py-1.5 tabular-nums">{c.value} {t('kgCO2e')}/{c.unit}</td>
                            <td className="px-2 py-1.5">{c.country}</td>
                            <td className="px-2 py-1.5">{c.tier}</td>
                            <td className="px-2 py-1.5"><StatusBadge status={c.status} /></td>
                            <td className="px-2 py-1.5 text-slate-500">{c.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {picked && !usable.some((c) => c.factor_id === picked) && (
                  <div className="space-y-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={proxy.confirmed} onChange={(e) => setProxy({ ...proxy, confirmed: e.target.checked })} />
                      {t('proxyConfirm')}
                    </label>
                    <Input label={t('proxyRationale')} value={proxy.why} onChange={(v) => setProxy({ ...proxy, why: v })} />
                  </div>
                )}
                {sg.excluded.length > 0 && (
                  <details className="rounded-lg border border-slate-200 p-2 text-xs text-slate-500">
                    <summary className="cursor-pointer font-medium text-slate-600">{t('excluded')} ({sg.excluded.length})</summary>
                    <ul className="mt-2 space-y-1">{sg.excluded.map((e) => <li key={e.factor_id}><b>{e.factor_id}</b> — {e.reason}</li>)}</ul>
                  </details>
                )}
              </>
            )}
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-3">
            <Input label={`${t('factorValue')} (kg CO₂e / ${t('unit')})`} type="number" step="any" value={manual.value} onChange={(v) => setManual({ ...manual, value: v })} />
            <Input label={t('factorManualSource')} value={manual.source} onChange={(v) => setManual({ ...manual, source: v })} />
            <Input label={`URL (${t('optional')})`} value={manual.url} onChange={(v) => setManual({ ...manual, url: v })} />
          </div>
        )}
      </Card>

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <Textarea label={t('notes')} value={f.notes} onChange={(v) => setF({ ...f, notes: v })} rows={2} className="min-w-64 flex-1" />
          <Input label={t('evidence')} value={f.evidence_ref} onChange={(v) => setF({ ...f, evidence_ref: v })} className="w-56" />
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={f.allow_duplicate} onChange={(e) => setF({ ...f, allow_duplicate: e.target.checked })} />
            {t('allowDuplicate')}
          </label>
          <Button onClick={save} disabled={busy || !f.activity_name || !f.quantity} className="ms-auto">
            {busy ? '…' : `💾 ${t('saveAndCalculate')}`}
          </Button>
        </div>
      </Card>

      {result && (
        <Card title={`✅ ${t('calculationResult')} #${result.record_id}`}>
          {result.record ? (
            <div className="grid gap-3 text-sm md:grid-cols-4">
              <div className="rounded-lg bg-brand-600 p-4 text-white">
                <div className="text-xs opacity-80">{t('total')}</div>
                <div className="text-2xl font-bold tabular-nums">{Number(result.record.kg_co2e ?? 0).toLocaleString()} kg</div>
                <div className="text-xs opacity-80">{(Number(result.record.kg_co2e ?? 0) / 1000).toFixed(4)} {t('tCO2e')}</div>
              </div>
              <div><div className="text-xs text-slate-400">{t('byScope')}</div><div className="font-medium">{result.record.scope ?? '—'}</div></div>
              <div><div className="text-xs text-slate-400">{t('calcStatus')}</div><StatusBadge status={result.record.calc_status} /></div>
              <div><div className="text-xs text-slate-400">{t('factor')}</div>
                <div className="text-xs text-slate-600">{result.record.factor_value} {result.record.factor_unit}</div>
                <div className="text-xs text-slate-400">{result.record.factor_source}</div></div>
            </div>
          ) : (
            <div className="text-sm text-amber-700">{result.status} — {result.notes}</div>
          )}
          <div className="mt-3 flex gap-2">
            <Button variant="outline" onClick={() => nav('/records')}>{t('navRecords')} →</Button>
          </div>
        </Card>
      )}
    </div>
  )
}
