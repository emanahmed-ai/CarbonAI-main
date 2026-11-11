import { useEffect, useState } from 'react'
import { api, download, errMsg } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Button, Card, Input, Select, Textarea } from '../components/ui'
import { useI18n } from '../i18n'

export default function Settings() {
  const { t, lang, setLang } = useI18n()
  const { user, refresh } = useAuth()
  const [s, setS] = useState<Record<string, string>>({})
  const [dbi, setDbi] = useState<any>(null)
  const [facilities, setFacilities] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const [pw, setPw] = useState({ old: '', new1: '' })
  const [backupFac, setBackupFac] = useState('')
  const [reset, setReset] = useState({ facility_id: '', password: '', reason: '', confirm: '' })
  const [resetResult, setResetResult] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const isAdmin = user?.role === 'admin'
  const isStaff = user?.role === 'admin' || user?.role === 'head_office'

  useEffect(() => {
    api.get('/settings').then((r) => setS(r.data))
    if (isStaff) {
      api.get('/org/facilities').then((r) => {
        setFacilities(r.data)
        if (r.data.length) { setBackupFac(String(r.data[0].facility_id)); setReset({ ...reset, facility_id: String(r.data[0].facility_id) }) }
      })
      api.get('/settings/db-info').then((r) => setDbi(r.data)).catch(() => {})
    }
  }, [isStaff])

  const save = async (key: string, value: string) => {
    setMsg('')
    try { await api.put('/settings', { key, value }); setMsg('✓ ' + t('success')) } catch (e) { setMsg(errMsg(e)) }
  }
  const backupDb = async () => {
    setMsg('')
    try { const r = await api.post('/settings/backup'); setMsg(`✓ ${r.data.path}`) } catch (e) { setMsg(errMsg(e)) }
  }
  const changePw = async () => {
    setMsg('')
    try {
      await api.post('/auth/change-password', { old_password: pw.old, new_password: pw.new1 })
      setPw({ old: '', new1: '' }); await refresh(); setMsg('✓ ' + t('success'))
    } catch (e) { setMsg(errMsg(e)) }
  }
  const backupZip = async () => {
    setMsg('')
    try {
      const q = backupFac ? `?facility_id=${backupFac}` : ''
      await download(`/settings/backup.zip${q}`, `carbonai_backup_${backupFac || 'all'}.zip`)
      setMsg('✓ ' + t('success'))
    } catch (e) { setMsg(errMsg(e)) }
  }
  const doReset = async () => {
    setMsg(''); setResetResult(null); setBusy(true)
    try {
      const r = await api.post('/settings/factory-reset', {
        password: reset.password, reason: reset.reason, confirm: reset.confirm,
        facility_id: reset.facility_id ? Number(reset.facility_id) : null,
      }, { timeout: 120_000 })
      setResetResult(r.data)
      setReset({ ...reset, password: '', confirm: '', reason: '' })
    } catch (e) { setMsg(errMsg(e)) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-slate-800">{t('navSettings')}</h1>
      {msg && <div className="rounded-lg bg-brand-50 px-4 py-2 text-sm text-brand-700">{msg}</div>}

      <Card title={t('navSettings')}>
        <div className="grid gap-3 md:grid-cols-4">
          <Select label={t('language')} value={lang} onChange={(v) => setLang(v as 'ar' | 'en')}
            options={[{ value: 'ar', label: 'العربية' }, { value: 'en', label: 'English' }]} />
          <Select label={t('displayUnit')} value={s.display_unit ?? 'tonne'} onChange={(v) => save('display_unit', v)}
            options={[{ value: 'tonne', label: t('tonne') }, { value: 'kg', label: 'kg' }]} />
          <Select label={t('defaultCountry')} value={s.default_country ?? 'EG'} onChange={(v) => save('default_country', v)}
            options={['EG', 'SA', 'AE', 'JO', 'QA', 'KW', 'OM', 'BH', 'MA', 'DZ', 'TN', 'SD', 'IQ', 'LB', 'PS', 'LY',
              'YE', 'TR', 'DE', 'FR', 'GB', 'IT', 'ES', 'NL', 'SE', 'CH', 'US', 'CA', 'MX', 'BR', 'IN', 'CN', 'JP',
              'KR', 'ID', 'PK', 'AU', 'NZ', 'ZA', 'NG', 'KE'].map((c) => ({ value: c, label: c }))} />
          <Select label={t('defaultScope2')} value={s.scope2_method ?? 'location'} onChange={(v) => save('scope2_method', v)}
            options={[{ value: 'location', label: t('location') }, { value: 'market', label: t('market') }]} />
        </div>
      </Card>

      <Card title={t('changePassword')}>
        <div className="flex flex-wrap items-end gap-3">
          <Input label={t('currentPassword')} type="password" value={pw.old} onChange={(v) => setPw({ ...pw, old: v })} className="w-56" />
          <Input label={t('newPassword')} type="password" value={pw.new1} onChange={(v) => setPw({ ...pw, new1: v })} className="w-56" />
          <Button onClick={changePw} disabled={pw.new1.length < 8}>{t('changePassword')}</Button>
        </div>
      </Card>

      {isStaff && (
        <Card title={t('backupTitle')}>
          <p className="mb-3 text-xs text-slate-400">{t('backupHint')}</p>
          <div className="flex flex-wrap items-end gap-3">
            <Select label={t('facility')} value={backupFac} onChange={setBackupFac} className="w-64"
              options={[{ value: '', label: t('all') }, ...facilities.map((f: any) => ({ value: String(f.facility_id), label: f.name }))]} />
            <Button onClick={backupZip}>⬇ {t('downloadBackup')}</Button>
          </div>
        </Card>
      )}

      {isStaff && (
        <Card title={t('resetTitle')}>
          <p className="mb-3 text-xs text-rose-600">{t('resetHint')}</p>
          <div className="grid gap-3 md:grid-cols-4">
            <Select label={t('facility')} value={reset.facility_id} onChange={(v) => setReset({ ...reset, facility_id: v })}
              options={facilities.map((f: any) => ({ value: String(f.facility_id), label: f.name }))} />
            <Input label={t('currentPassword')} type="password" value={reset.password} onChange={(v) => setReset({ ...reset, password: v })} />
            <Textarea label={t('resetReason')} value={reset.reason} onChange={(v) => setReset({ ...reset, reason: v })} rows={1} />
            <Input label={t('resetConfirm')} value={reset.confirm} onChange={(v) => setReset({ ...reset, confirm: v })} placeholder="DELETE" />
          </div>
          <Button variant="danger" className="mt-3" onClick={doReset}
            disabled={busy || !reset.password || reset.confirm.trim().toUpperCase() !== 'DELETE' || !reset.facility_id}>
            🗑 {t('resetTitle')}
          </Button>
          {resetResult && (
            <div className="mt-3 rounded-lg bg-rose-50 p-3 text-xs text-rose-800">
              <div className="font-semibold">✓ {t('resetDone')}</div>
              <div>{t('deletedCounts')}: {JSON.stringify(resetResult.deleted)}</div>
              <div>{t('backup')}: {resetResult.backup}</div>
            </div>
          )}
        </Card>
      )}

      {isAdmin && (
        <Card title={t('dbInfo')} actions={<Button variant="outline" onClick={backupDb}>💾 {t('backupNow')}</Button>}>
          {dbi && (
            <div className="space-y-2 text-sm">
              <div className="text-xs text-slate-400">{dbi.path}</div>
              <div className="grid grid-cols-3 gap-2 md:grid-cols-7">
                {Object.entries(dbi.counts).map(([k, v]) => (
                  <div key={k} className="rounded-lg bg-slate-50 p-2 text-center">
                    <div className="text-lg font-bold tabular-nums text-slate-700">{String(v)}</div>
                    <div className="text-[10px] text-slate-400">{k}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
