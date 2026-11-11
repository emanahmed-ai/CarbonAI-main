import { useEffect, useState } from 'react'
import { api, download } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Button, Card, Select } from '../components/ui'
import { useI18n } from '../i18n'

export default function Reports() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [facilities, setFacilities] = useState<any[]>([])
  const [f, setF] = useState({ year: String(new Date().getFullYear()), month: 'all', facility: 'all', scope: 'all' })
  const isStaff = user?.role === 'admin' || user?.role === 'head_office'

  useEffect(() => {
    if (isStaff) api.get('/org/facilities').then((r) => setFacilities(r.data))
  }, [isStaff])

  const qs = () => {
    const p = new URLSearchParams()
    if (f.year !== 'all') p.set('year', f.year)
    if (f.month !== 'all') p.set('month', f.month)
    if (f.facility !== 'all') p.set('facility_id', f.facility)
    if (f.scope !== 'all') p.set('scope', f.scope)
    return p.toString()
  }
  const period = () => `${f.year === 'all' ? 'all' : f.year}${f.month !== 'all' ? `-${String(f.month).padStart(2, '0')}` : ''}`
  const annualYear = f.year !== 'all' ? f.year : String(new Date().getFullYear())

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-slate-800">{t('navReports')}</h1>
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <Select label={t('year')} value={f.year} onChange={(v) => setF({ ...f, year: v })} className="w-32"
            options={['all', ...Array.from({ length: 7 }, (_, i) => String(new Date().getFullYear() - i))].map((y) => ({ value: y, label: y === 'all' ? t('all') : y }))} />
          <Select label={t('month')} value={f.month} onChange={(v) => setF({ ...f, month: v })} className="w-32"
            options={[{ value: 'all', label: t('all') }, ...Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) }))]} />
          <Select label={t('byScope')} value={f.scope} onChange={(v) => setF({ ...f, scope: v })} className="w-32"
            options={[{ value: 'all', label: t('all') }, ...['Scope 1', 'Scope 2', 'Scope 3'].map((s) => ({ value: s, label: s }))]} />
          {isStaff && (
            <Select label={t('facility')} value={f.facility} onChange={(v) => setF({ ...f, facility: v })} className="w-56"
              options={[{ value: 'all', label: t('all') }, ...facilities.map((x: any) => ({ value: String(x.facility_id), label: x.name }))]} />
          )}
        </div>
      </Card>
      <div className="flex flex-wrap gap-3">
        <Button onClick={() => download(`/reports/csv?${qs()}`, `carbonai_records_${period()}.csv`)}>📄 {t('downloadCsv')}</Button>
        <Button variant="outline" onClick={() => download(`/reports/monthly-csv?${qs()}`, `carbonai_monthly_${period()}.csv`)}>📊 {t('monthlySummaryCsv')}</Button>
        <Button variant="outline" onClick={() => download(`/reports/pdf?${qs()}&lang=en`, `carbonai_report_${period()}_en.pdf`)}>🧾 {t('downloadPdfEn')}</Button>
        <Button variant="outline" onClick={() => download(`/reports/pdf?${qs()}&lang=ar`, `carbonai_report_${period()}_ar.pdf`)}>🧾 {t('downloadPdfAr')}</Button>
      </div>
      <Card title="Detailed management report (charts embedded)">
        <p className="mb-3 text-xs text-slate-400">
          Executive summary, scope shares, charts (scope distribution, monthly trend, facility and annual comparison),
          top sources, reduction plans + targets, methodology and limitations — inside the PDF itself.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => download(`/reports/pdf-detailed?${qs()}&lang=en`, `carbonai_detailed_${period()}_en.pdf`)}>📘 Detailed PDF (EN)</Button>
          <Button variant="outline" onClick={() => download(`/reports/pdf-detailed?${qs()}&lang=ar`, `carbonai_detailed_${period()}_ar.pdf`)}>📘 تقرير تفصيلي (AR)</Button>
          <Button variant="outline" onClick={() => download(`/reports/annual?year=${annualYear}${f.facility !== 'all' ? `&facility_id=${f.facility}` : ''}&lang=en`, `carbonai_annual_${annualYear}_en.pdf`)}>
            📅 Annual report {annualYear} (EN)
          </Button>
          <Button variant="outline" onClick={() => download(`/reports/annual?year=${annualYear}${f.facility !== 'all' ? `&facility_id=${f.facility}` : ''}&lang=ar`, `carbonai_annual_${annualYear}_ar.pdf`)}>
            📅 التقرير السنوي {annualYear} (AR)
          </Button>
        </div>
      </Card>
      <Card>
        <p className="text-xs leading-5 text-slate-400">
          جميع التقارير تستخدم نفس فلاتر لوحة التحكم ونفس منطق الحساب (سجلات «محسوبة» فقط). لا تُدمج الفترات السنوية والشهرية مع الإجمالي التراكمي.
          All reports use the same filters and the same summarize() path as the dashboard; annual, monthly and lifetime totals are never mixed.
        </p>
      </Card>
    </div>
  )
}
