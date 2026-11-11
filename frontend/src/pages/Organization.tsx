import { useCallback, useEffect, useState } from 'react'
import { api, errMsg } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Button, Card, DataTable, Input, Select } from '../components/ui'
import { useI18n } from '../i18n'

export default function Organization() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [companies, setCompanies] = useState<any[]>([])
  const [facilities, setFacilities] = useState<any[]>([])
  const [msg, setMsg] = useState('')
  const [nf, setNf] = useState({ name: '', company_id: '', country_code: 'EG', internal_ref: '', control_status: 'owned_controlled' })
  const isAdmin = user?.role === 'admin'

  const load = useCallback(() => {
    api.get('/org/companies').then((r) => setCompanies(r.data))
    api.get('/org/facilities').then((r) => setFacilities(r.data))
  }, [])
  useEffect(load, [load])

  const addFacility = async () => {
    setMsg('')
    try {
      await api.post('/org/facilities', {
        name: nf.name, country_code: nf.country_code || null, internal_ref: nf.internal_ref || null,
        control_status: nf.control_status, company_id: nf.company_id ? Number(nf.company_id) : undefined,
      })
      setNf({ ...nf, name: '', internal_ref: '' }); load()
    } catch (e) { setMsg(errMsg(e)) }
  }
  const addCompany = async () => {
    setMsg('')
    const name = (window.prompt(`${t('newCompany')} — ${t('name')}:`) || '').trim()
    if (!name) return
    try { await api.post('/org/companies', { name }); load() } catch (e) { setMsg(errMsg(e)) }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="me-auto text-xl font-bold text-slate-800">{t('navOrganization')}</h1>
        {isAdmin && <Button variant="outline" onClick={addCompany}>+ {t('newCompany')}</Button>}
      </div>
      {msg && <div className="rounded-lg bg-rose-50 px-4 py-2 text-sm text-rose-700">{msg}</div>}

      <Card title={t('facilities')}>
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <Input label={t('newFacility')} value={nf.name} onChange={(v) => setNf({ ...nf, name: v })} className="w-64" />
          {isAdmin && (
            <Select label="Company" value={nf.company_id} onChange={(v) => setNf({ ...nf, company_id: v })} className="w-52"
              options={[{ value: '', label: '—' }, ...companies.map((c) => ({ value: String(c.company_id), label: c.name }))]} />
          )}
          <Select label={t('country')} value={nf.country_code} onChange={(v) => setNf({ ...nf, country_code: v })} className="w-28"
            options={[{ value: '', label: '—' }, ['EG', 'SA', 'AE', 'JO', 'QA', 'KW', 'OM', 'BH', 'MA', 'DZ', 'TN', 'SD', 'IQ', 'LB', 'LY'].map((c) => ({ value: c, label: c }))].flat()} />
          <Select label={t('controlStatus')} value={nf.control_status} onChange={(v) => setNf({ ...nf, control_status: v })} className="w-44"
            options={['owned_controlled', 'leased_controlled', 'leased_not_controlled', 'not_controlled', 'unknown'].map((c) => ({ value: c, label: c }))} />
          <Button onClick={addFacility} disabled={!nf.name.trim()}>+ {t('create')}</Button>
        </div>
        <DataTable rows={facilities} pageSize={12} columns={[
          { key: 'facility_id', label: '#', sortable: true },
          { key: 'name', label: t('name') },
          { key: 'company_name', label: 'Company' },
          { key: 'country_code', label: t('country') },
          { key: 'control_status', label: t('controlStatus') },
          { key: 'n_records', label: t('records'), sortable: true },
        ]} />
      </Card>

      <Card title={t('companies')}>
        <DataTable rows={companies} pageSize={8} columns={[
          { key: 'company_id', label: '#' },
          { key: 'name', label: t('name') },
          { key: 'country_code', label: t('country') },
          { key: 'industry_sector', label: 'Sector' },
          { key: 'boundary_approach', label: 'Boundary' },
          { key: 'n_facilities', label: t('facilities') },
        ]} />
      </Card>
    </div>
  )
}
