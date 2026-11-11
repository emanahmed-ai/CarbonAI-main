import { useCallback, useEffect, useState } from 'react'
import { api, errMsg } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Badge, Button, Card, DataTable, Input, Modal, Select, StatusBadge } from '../components/ui'
import { useI18n, type DictKey } from '../i18n'

export default function Users() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [rows, setRows] = useState<any[]>([])
  const [facilities, setFacilities] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const [form, setForm] = useState({ username: '', password: '', role: 'factory_manager', full_name: '', email: '', facility_id: '' })
  const [reset, setReset] = useState<{ id: number; username: string; password: string } | null>(null)

  const isAdmin = user?.role === 'admin'
  const load = useCallback(() => { api.get('/users').then((r) => setRows(r.data)) }, [])
  useEffect(load, [load])
  useEffect(() => { api.get('/org/facilities').then((r) => setFacilities(r.data)) }, [])

  const add = async () => {
    setMsg('')
    try {
      await api.post('/users', {
        username: form.username, password: form.password, role: form.role,
        full_name: form.full_name || null, email: form.email || null,
        facility_id: form.facility_id ? Number(form.facility_id) : null,
      })
      setForm({ username: '', password: '', role: 'factory_manager', full_name: '', email: '', facility_id: '' })
      load()
    } catch (e) { setMsg(errMsg(e)) }
  }

  const toggle = async (r: any) => {
    setMsg('')
    try { await api.patch(`/users/${r.user_id}`, { is_active: !r.is_active }); load() } catch (e) { setMsg(errMsg(e)) }
  }
  const doReset = async () => {
    if (!reset) return
    setMsg('')
    try { await api.post(`/users/${reset.id}/password`, { new_password: reset.password }); setReset(null) } catch (e) { setMsg(errMsg(e)) }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-slate-800">{t('navUsers')}</h1>
      {msg && <div className="rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-700">{msg}</div>}

      <Card title={t('addUser')}>
        <div className="grid gap-3 md:grid-cols-3">
          <Input label={t('username')} value={form.username} onChange={(v) => setForm({ ...form, username: v })} />
          <Input label={t('password')} value={form.password} onChange={(v) => setForm({ ...form, password: v })} type="password" />
          <Select label={t('role')} value={form.role} onChange={(v) => setForm({ ...form, role: v })}
            options={['factory_manager', 'viewer', 'head_office', ...(isAdmin ? ['admin'] : [])].map((r) => ({ value: r, label: t(`roles.${r}` as DictKey) }))} />
          <Input label={t('full_name')} value={form.full_name} onChange={(v) => setForm({ ...form, full_name: v })} />
          <Input label={t('email')} value={form.email} onChange={(v) => setForm({ ...form, email: v })} />
          {(form.role === 'factory_manager' || form.role === 'viewer') && (
            <Select label={t('facility')} value={form.facility_id} onChange={(v) => setForm({ ...form, facility_id: v })}
              options={[{ value: '', label: '—' }, ...facilities.map((f: any) => ({ value: String(f.facility_id), label: f.name }))]} />
          )}
        </div>
        <Button onClick={add} className="mt-3" disabled={!form.username || form.password.length < 8}>{t('create')}</Button>
      </Card>

      <DataTable rows={rows} pageSize={12} columns={[
        { key: 'username', label: t('username'), render: (r) => <span className="font-medium">{r.username}</span> },
        { key: 'full_name', label: t('full_name') },
        { key: 'role', label: t('role'), render: (r) => <Badge tone={r.role === 'admin' ? 'purple' : r.role === 'head_office' ? 'blue' : 'green'}>{t(`roles.${r.role}` as DictKey)}</Badge> },
        { key: 'facility_name', label: t('facility') },
        { key: 'company_name', label: 'Company' },
        { key: 'is_active', label: t('status'), render: (r) => <StatusBadge status={r.is_active ? 'done' : 'cancelled'} /> },
        { key: 'last_login_at', label: 'Last login', render: (r) => String(r.last_login_at ?? '—').slice(0, 16) },
        { key: 'act', label: t('actions'), render: (r) => (
          <span className="flex gap-1">
            <Button variant="outline" className="!px-2 !py-1 text-xs" onClick={() => toggle(r)}>{r.is_active ? t('inactive') : t('active')}</Button>
            {isAdmin && <Button variant="outline" className="!px-2 !py-1 text-xs" onClick={() => setReset({ id: r.user_id, username: r.username, password: '' })}>🔑</Button>}
          </span>
        ) },
      ]} />

      <Modal open={!!reset} title={`${t('resetPassword')} — ${reset?.username}`} onClose={() => setReset(null)}>
        {reset && (
          <div className="space-y-3">
            <Input label={t('newPassword')} value={reset.password} onChange={(v) => setReset({ ...reset, password: v })} type="password" />
            <Button onClick={doReset} disabled={reset.password.length < 8}>{t('save')}</Button>
          </div>
        )}
      </Modal>
    </div>
  )
}
