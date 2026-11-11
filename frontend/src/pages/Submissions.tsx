import { useCallback, useEffect, useState } from 'react'
import { api, errMsg } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Badge, Button, Card, DataTable, Input, Modal, Select, StatusBadge, fmtKg } from '../components/ui'
import { useI18n } from '../i18n'

type Sub = Record<string, any>

export default function Submissions() {
  const { t } = useI18n()
  const { user } = useAuth()
  const isStaff = user?.role === 'admin' || user?.role === 'head_office'
  const [subs, setSubs] = useState<Sub[]>([])
  const [facilities, setFacilities] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const [form, setForm] = useState({ facility_id: '', year: String(new Date().getFullYear()), month: 'all', title: '', allow_supersede: false })
  const [busy, setBusy] = useState(false)
  const [review, setReview] = useState<{ sub: Sub; decision: string; note: string } | null>(null)
  const [detail, setDetail] = useState<Sub | null>(null)

  const load = useCallback(() => { api.get('/submissions').then((r) => setSubs(r.data)) }, [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (isStaff) api.get('/org/facilities').then((r) => setFacilities(r.data))
  }, [isStaff])

  const submit = async () => {
    setMsg(''); setBusy(true)
    try {
      await api.post('/submissions', {
        facility_id: form.facility_id ? Number(form.facility_id) : undefined,
        period_year: Number(form.year),
        period_month: form.month === 'all' ? null : Number(form.month),
        title: form.title, allow_supersede: form.allow_supersede,
      })
      setForm({ ...form, title: '', allow_supersede: false })
      load()
    } catch (e) { setMsg(errMsg(e)) } finally { setBusy(false) }
  }

  const doReview = async () => {
    if (!review) return
    setMsg('')
    try {
      await api.post(`/submissions/${review.sub.submission_id}/review`, { decision: review.decision, note: review.note })
      setReview(null); load()
    } catch (e) { setMsg(errMsg(e)) }
  }

  const cols: any[] = [
    { key: 'submission_id', label: '#', sortable: true },
    { key: 'facility_name', label: t('facility') },
    { key: 'period', label: t('submissionPeriod'), render: (r: Sub) => `${r.period_year}${r.period_month ? `-${String(r.period_month).padStart(2, '0')}` : ''}` },
    { key: 'total_kg_co2e', label: t('total'), sortable: true, render: (r: Sub) => `${fmtKg(r.total_kg_co2e)} kg` },
    { key: 'calculated_count', label: t('calculated') },
    { key: 'needs_review_count', label: t('needsReview') },
    { key: 'status', label: t('status'), render: (r: Sub) => <StatusBadge status={r.status} /> },
    { key: 'submitted_by', label: t('submittedBy') },
  ]
  if (isStaff) {
    cols.push({
      key: 'review_actions', label: t('actions'),
      render: (r: Sub) => (r.status === 'submitted' ? (
        <span className="flex gap-1" onClick={(e) => e.stopPropagation()}>
          <Button variant="primary" className="!px-2 !py-1 text-xs" onClick={() => setReview({ sub: r, decision: 'approve', note: '' })}>✓</Button>
          <Button variant="danger" className="!px-2 !py-1 text-xs" onClick={() => setReview({ sub: r, decision: 'reject', note: '' })}>✕</Button>
        </span>
      ) : <span className="text-xs text-slate-400">{r.reviewed_by ?? '—'}</span>),
    })
  } else {
    cols.push({ key: 'reviewed_by', label: t('reviewedBy') })
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-slate-800">{t('navSubmissions')}</h1>
      {msg && <div className="rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-700 ring-1 ring-inset ring-rose-600/20">{msg}</div>}

      <Card title={t('submitReport')}>
        <div className="flex flex-wrap items-end gap-3">
          {isStaff && (
            <Select label={t('facility')} value={form.facility_id} onChange={(v) => setForm({ ...form, facility_id: v })} className="w-56"
              options={[{ value: '', label: '—' }, ...facilities.map((f: any) => ({ value: String(f.facility_id), label: f.name }))]} />
          )}
          <Select label={t('year')} value={form.year} onChange={(v) => setForm({ ...form, year: v })} className="w-28"
            options={Array.from({ length: 7 }, (_, i) => ({ value: String(new Date().getFullYear() - i), label: String(new Date().getFullYear() - i) }))} />
          <Select label={t('month')} value={form.month} onChange={(v) => setForm({ ...form, month: v })} className="w-36"
            options={[{ value: 'all', label: t('fullYear') }, ...Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) }))]} />
          <Input label={t('name')} value={form.title} onChange={(v) => setForm({ ...form, title: v })} className="w-64" />
          <label className="flex items-center gap-2 pb-2 text-xs text-slate-500">
            <input type="checkbox" checked={form.allow_supersede} onChange={(e) => setForm({ ...form, allow_supersede: e.target.checked })} />
            استبدال تقرير مُرسل سابقًا / replace an earlier submitted draft
          </label>
          <Button onClick={submit} disabled={busy || (!isStaff ? false : !form.facility_id)} className="ms-auto">📨 {t('submitReport')}</Button>
        </div>
      </Card>

      <Card title={t('submissions')}>
        <DataTable<Sub>
          rows={subs}
          onRowClick={(r) => setDetail(r)}
          columns={cols}
        />
      </Card>

      <Modal open={!!review} title={review?.decision === 'approve' ? `✓ ${t('approve')}` : `✕ ${t('reject' as any)}`} onClose={() => setReview(null)}>
        {review && (
          <div className="space-y-3 text-sm">
            <div className="rounded bg-slate-50 p-3">
              <b>{review.sub.facility_name}</b> — {review.sub.period_year}
              {review.sub.period_month ? `-${String(review.sub.period_month).padStart(2, '0')}` : ''} ·{' '}
              {fmtKg(review.sub.total_kg_co2e)} kg CO₂e · {review.sub.calculated_count} {t('calculated')}
            </div>
            <Input label={t('reviewNote')} value={review.note} onChange={(v) => setReview({ ...review, note: v })} />
            <div className="flex gap-2">
              <Button variant={review.decision === 'approve' ? 'primary' : 'danger'} onClick={doReview}
                disabled={review.decision === 'reject' && !review.note.trim()}>
                {review.decision === 'approve' ? t('approve') : t('reject')}
              </Button>
              <Button variant="ghost" onClick={() => setReview(null)}>{t('cancel')}</Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={!!detail} title={`${t('navSubmissions')} #${detail?.submission_id}`} onClose={() => setDetail(null)} wide>
        {detail && (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">
              <StatusBadge status={detail.status} />
              <Badge tone="gray">{detail.facility_name}</Badge>
              <Badge tone="gray">{detail.period_year}{detail.period_month ? `-${String(detail.period_month).padStart(2, '0')}` : ''}</Badge>
              <Badge tone="blue">{fmtKg(detail.total_kg_co2e)} kg CO₂e</Badge>
            </div>
            {detail.review_note && <div className="rounded bg-amber-50 p-2 text-xs text-amber-800">💬 {detail.review_note}</div>}
            <table className="min-w-full text-xs">
              <thead className="bg-slate-50 text-slate-500">
                <tr>{[t('activityName'), t('byScope'), t('quantity'), t('kgCO2e'), t('calcStatus')].map((h) => <th key={h} className="px-2 py-1.5 text-start">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {detail.records.map((r: any) => (
                  <tr key={r.record_id}>
                    <td className="px-2 py-1.5">{r.activity_name}</td>
                    <td className="px-2 py-1.5">{r.scope ?? '—'}</td>
                    <td className="px-2 py-1.5">{r.quantity} {r.unit}</td>
                    <td className="px-2 py-1.5 tabular-nums">{r.kg_co2e ?? '—'}</td>
                    <td className="px-2 py-1.5">{r.calc_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>
    </div>
  )
}
