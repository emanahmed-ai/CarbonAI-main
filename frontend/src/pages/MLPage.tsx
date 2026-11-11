import { useCallback, useEffect, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, errMsg } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Badge, Button, Card, DataTable, Input, Select, Spinner, StatusBadge } from '../components/ui'
import { useI18n } from '../i18n'

type Model = Record<string, any>
type Forecast = {
  status: string; reason?: string
  data: { months_available: number; records: number; latest: string | null; ready: boolean }
  actual: { month: string; kg: number }[]
  forecast: { month: string; kg: number; lo_kg: number; hi_kg: number }[]
  model: Model | null
  annual_forecast_kg: number | null
  band_note?: string
}

export default function MLPage() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [status, setStatus] = useState<any>(null)
  const [fc, setFc] = useState<Forecast | null>(null)
  const [horizon, setHorizon] = useState('12')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [pred, setPred] = useState<any>(null)
  const [form, setForm] = useState({ quantity: '', unit: 'kWh', category_key: 'electricity', scope: 'Scope 2', month: String(new Date().getMonth() + 1) })
  const [meta, setMeta] = useState<any>(null)
  const isAdmin = user?.role === 'admin'

  const loadStatus = useCallback(() => api.get('/ml/status').then((r) => setStatus(r.data)), [])
  const loadForecast = useCallback(() => api.get('/ml/forecast', { params: { horizon: Number(horizon) } })
    .then((r) => setFc(r.data)).catch((e) => setMsg(errMsg(e))), [horizon])
  useEffect(() => { loadStatus() }, [loadStatus])
  useEffect(() => { loadForecast() }, [loadForecast])
  useEffect(() => { api.get('/records/meta').then((r) => setMeta(r.data)) }, [])

  const train = async () => {
    setMsg(''); setBusy(true)
    try {
      const r = await api.post('/ml/train', { horizon: Number(horizon) })
      setMsg(r.data.skipped ? `ℹ️ ${r.data.reason}` : `✓ model v${r.data.version} staged (${r.data.candidate}); activate it below.`)
      loadStatus(); loadForecast()
    } catch (e) { setMsg(errMsg(e)) } finally { setBusy(false) }
  }
  const activate = async (id: number) => {
    setMsg('')
    try { await api.post(`/ml/models/${id}/activate`); setMsg('✓ activated'); loadStatus(); loadForecast() } catch (e) { setMsg(errMsg(e)) }
  }
  const predict = async () => {
    setMsg(''); setPred(null); setBusy(true)
    try {
      const r = await api.post('/ml/predict', {
        quantity: Number(form.quantity), unit: form.unit, category_key: form.category_key,
        scope: form.scope, activity_month: Number(form.month),
      })
      setPred(r.data)
    } catch (e) { setMsg(errMsg(e)) } finally { setBusy(false) }
  }
  if (!status) return <Spinner label={t('loading')} />

  const chartData = fc ? [
    ...fc.actual.slice(-18).map((p) => ({ month: p.month, actual: p.kg, forecast: null as any })),
    ...fc.forecast.map((p) => ({ month: p.month, actual: null as any, forecast: p.kg, lo: p.lo_kg, hi: p.hi_kg })),
  ] : []

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-slate-800">{t('navML')}</h1>
      {msg && <div className="rounded-lg bg-brand-50 px-4 py-2 text-sm text-brand-800 ring-1 ring-inset ring-brand-600/20">{msg}</div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title={t('trainingData')}>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between"><span className="text-slate-400">{t('monthsAvailable')}</span><b className="tabular-nums">{fc?.data.months_available ?? '—'}</b></div>
            <div className="flex justify-between"><span className="text-slate-400">{t('records')}</span><b className="tabular-nums">{fc?.data.records ?? '—'}</b></div>
            <div className="flex justify-between"><span className="text-slate-400">latest month</span><b>{fc?.data.latest ?? '—'}</b></div>
            <div className="pt-2">
              {fc?.data.ready
                ? <Badge tone="green">✓ 12+ consecutive months</Badge>
                : <Badge tone="amber">{t('insufficientData')}</Badge>}
            </div>
            <p className="text-[11px] text-slate-400">Forecast eligibility: ≥ {status.data_readiness.min_months_required} consecutive months of calculated emissions.</p>
          </div>
        </Card>
        <Card title={t('forecast') + ' — model'}>
          {fc?.model ? (
            <div className="space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-slate-400">model</span><b>v{fc.model.version} · {fc.model.candidate}</b></div>
              <div className="flex justify-between"><span className="text-slate-400">trained</span><span>{String(fc.model.trained_at).slice(0, 10)}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">range</span><span>{fc.model.train_range?.join(' → ')}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">MAE</span><span className="tabular-nums">{fc.model.metrics?.[fc.model.candidate]?.mae_kg ?? fc.model.metrics?.mae_kg ?? '—'} kg</span></div>
              <div className="flex justify-between"><span className="text-slate-400">R²</span><span className="tabular-nums">{fc.model.metrics?.[fc.model.candidate]?.r2 ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">baseline MAE</span><span className="tabular-nums">{fc.model.metrics?.seasonal_naive?.mae_kg ?? '—'} kg</span></div>
            </div>
          ) : (
            <div className="text-xs text-slate-500">
              {fc?.status === 'NO_ACTIVE_MODEL' ? t('noActiveModel') : fc?.reason ?? '—'}
              {isAdmin && (
                <Button onClick={train} disabled={busy} className="mt-2 w-full">⚙ {t('trainModel')}</Button>
              )}
            </div>
          )}
        </Card>
        <Card title="controls">
          <div className="space-y-2">
            <Select label={t('horizon')} value={horizon} onChange={setHorizon}
              options={['1', '3', '6', '12'].map((h) => ({ value: h, label: `${h} months` }))} />
            {isAdmin && <Button onClick={train} disabled={busy} className="w-full">⚙ {t('trainModel')}</Button>}
            {fc?.annual_forecast_kg != null && (
              <div className="rounded-lg bg-violet-50 p-3 text-sm">
                <div className="text-xs text-violet-600">{t('annualForecast')}</div>
                <div className="text-xl font-bold tabular-nums text-violet-800">{fc.annual_forecast_kg.toLocaleString()} kg</div>
              </div>
            )}
          </div>
        </Card>
      </div>

      {fc && fc.status === 'OK' && (
        <Card title={t('actualVsPredicted')}>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="month" fontSize={10} />
              <YAxis fontSize={10} />
              <Tooltip formatter={(v: number) => `${v?.toLocaleString?.() ?? v} kg`} />
              <Legend iconSize={10} formatter={(v) => <span className="text-xs">{v}</span>} />
              <Line type="monotone" dataKey="actual" name={t('actual')} stroke="#059669" strokeWidth={2} dot={{ r: 2 }} connectNulls={false} />
              <Line type="monotone" dataKey="forecast" name={t('forecast')} stroke="#7c3aed" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 2 }} connectNulls={false} />
              <Line type="monotone" dataKey="hi" name="band" stroke="#c4b5fd" strokeWidth={1} dot={false} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-1 text-[11px] text-slate-400">{fc.band_note}</p>
        </Card>
      )}

      {status.forecast_models?.length > 0 && (
        <Card title={t('modelVersions')}>
          <DataTable rows={status.forecast_models} pageSize={8} columns={[
            { key: 'model_id', label: '#' },
            { key: 'name', label: 'name' },
            { key: 'version', label: 'v' },
            { key: 'trained_date', label: t('createdAt'), render: (r: Model) => String(r.created_at).slice(0, 19) },
            { key: 'n_records', label: 'months' },
            { key: 'metrics', label: 'MAE', render: (r: Model) => `${r.metrics?.mae_kg ?? '—'} kg` },
            { key: 'status', label: t('status'), render: (r: Model) => <StatusBadge status={r.status === 'active' ? 'approved' : r.status === 'staged' ? 'submitted' : 'withdrawn'} /> },
            ...(isAdmin ? [{
              key: 'act', label: '', render: (r: Model) => r.status !== 'active'
                ? <Button variant="outline" className="!px-2 !py-1 text-xs" onClick={() => activate(r.model_id)}>{t('activateModel')}</Button>
                : '—',
            } as any] : []),
          ]} />
        </Card>
      )}

      <Card title={t('mlPredict') + ' (row estimate)'}>
        <div className="flex flex-wrap items-end gap-3">
          <Input label={t('quantity')} type="number" step="any" value={form.quantity} onChange={(v) => setForm({ ...form, quantity: v })} className="w-36" />
          <Select label={t('unit')} value={form.unit} onChange={(v) => setForm({ ...form, unit: v })} className="w-28"
            options={(meta?.units ?? ['kWh']).map((u: string) => ({ value: u, label: u }))} />
          <Select label={t('category')} value={form.category_key} onChange={(v) => setForm({ ...form, category_key: v })} className="w-48"
            options={(meta?.categories ?? []).map((c: any) => ({ value: c.category_key, label: c.category_key }))} />
          <Select label={t('byScope')} value={form.scope} onChange={(v) => setForm({ ...form, scope: v })} className="w-32"
            options={['Scope 1', 'Scope 2', 'Scope 3'].map((s) => ({ value: s, label: s }))} />
          <Select label={t('month')} value={form.month} onChange={(v) => setForm({ ...form, month: v })} className="w-24"
            options={Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) }))} />
          <Button onClick={predict} disabled={busy || !form.quantity || !status.row_estimate_model?.loaded}>🔮 {t('mlPredict')}</Button>
        </div>
        {!status.row_estimate_model?.loaded && (
          <p className="mt-2 text-xs text-slate-400">{status.row_estimate_model?.reason}</p>
        )}
        {pred && (
          <div className="mt-3 rounded-xl bg-gradient-to-br from-violet-500 to-violet-700 p-4 text-white">
            <div className="text-xs opacity-80">{t('predicted')}</div>
            <div className="text-2xl font-bold tabular-nums">{pred.predicted_kg_co2e.toLocaleString()} kg CO₂e</div>
            <div className="text-xs opacity-75">{pred.disclaimer}</div>
          </div>
        )}
      </Card>
    </div>
  )
}
