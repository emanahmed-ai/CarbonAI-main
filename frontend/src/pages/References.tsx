import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { Badge, Card, Input, Select, Spinner } from '../components/ui'
import { useI18n } from '../i18n'

const KIND_LABEL: Record<string, [string, string, any]> = {
  standard: ['معايير', 'Standards', 'purple'],
  methodology: ['منهجيات', 'Methodologies', 'blue'],
  factor_database: ['قواعد معاملات', 'Factor databases', 'green'],
  gwp: ['قيم GWP', 'GWP values', 'amber'],
  national_inventory: ['تقارير وطنية', 'National inventories', 'gray'],
}

export default function References() {
  const { t } = useI18n()
  const [rows, setRows] = useState<any[]>([])
  const [kind, setKind] = useState('all')
  const [country, setCountry] = useState('all')
  const [q, setQ] = useState('')

  useEffect(() => {
    api.get('/references', { params: { kind: kind === 'all' ? undefined : kind, country: country === 'all' ? undefined : country, q: q || undefined } })
      .then((r) => setRows(r.data))
  }, [kind, country, q])

  const grouped = rows.reduce((acc: Record<string, any[]>, r) => {
    (acc[r.kind] ??= []).push(r)
    return acc
  }, {})

  if (!rows.length && kind === 'all' && !q) return <Spinner label={t('loading')} />

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-slate-800">{t('navReferences')}</h1>
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <Select label={t('category')} value={kind} onChange={setKind} className="w-56"
            options={[{ value: 'all', label: t('all') }, ...Object.entries(KIND_LABEL).map(([k, v]) => ({ value: k, label: v[0] + ' / ' + v[1] }))]} />
          <Select label={t('country')} value={country} onChange={setCountry} className="w-36"
            options={[{ value: 'all', label: t('all') }, { value: 'EG', label: 'Egypt' }, { value: 'GLOBAL', label: 'Global' }]} />
          <Input label={t('search')} value={q} onChange={setQ} className="w-64" />
        </div>
        <p className="mt-2 text-[11px] text-slate-400">
          المعايير (ISO / GHG Protocol) تحدد المتطلبات والمنهجية وليست قاعدة معاملات. قيم GWP منفصلة عن معاملات الأنشطة.
          Standards define requirements; they are not factor databases. GWP values are separate from activity factors.
        </p>
      </Card>

      {Object.entries(grouped).map(([k, list]) => {
        const lbl = KIND_LABEL[k] ?? [k, k, 'gray']
        return (
          <Card key={k} title={<span className="flex items-center gap-2">{lbl[0]} / {lbl[1]} <Badge tone={lbl[2]}>{list.length}</Badge></span>}>
            <div className="space-y-3">
              {list.map((r: any) => (
                <div key={r.ref_key} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <b className="text-sm text-slate-800">{r.title}</b>
                    {r.country_applicability === 'EG' && <Badge tone="green">Egypt</Badge>}
                    {r.url
                      ? <a className="ms-auto text-xs font-medium text-brand-600 hover:underline" href={r.url} target="_blank" rel="noreferrer">{r.url}</a>
                      : <span className="ms-auto text-xs text-slate-400">{t('urlNotVerified')}</span>}
                  </div>
                  <div className="mt-1 grid gap-x-4 gap-y-1 text-xs text-slate-500 md:grid-cols-3">
                    <span><b>{r.organization}</b></span>
                    <span>{r.edition}{r.publication_year ? ` · ${r.publication_year}` : ''}</span>
                    <span>{r.access_date}</span>
                    <span className="md:col-span-2">{r.sectors}</span>
                    <span>{r.chapter_section}</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-400">{r.methodology_support}</div>
                  {r.notes && <div className="mt-1 text-[11px] text-slate-400">ℹ {r.notes}</div>}
                </div>
              ))}
            </div>
          </Card>
        )
      })}
    </div>
  )
}
