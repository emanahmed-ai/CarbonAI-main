import { useI18n } from '../i18n'
import { fmtKg } from './ui'

export type SummaryKpi = {
  total_kg_co2e: string
  total_t_co2e: string
  scopes_kpi: { scope: string; kg: string; share_pct: number | null; change_pct: number | null; comparable: boolean }[]
  comparison: { baseline_label: string; comparable: boolean; change_pct: number | null } | null
  records: number
  calculated: number
  needs_review: number
  verified_pct: number | null
  avg_monthly_active_kg: string | null
}

/** Shared KPI block: used by the dashboard AND the reduction-plans page (no copy-paste). */
export default function KpiCards({ s }: { s: SummaryKpi }) {
  const { t } = useI18n()
  const kpiBy = (name: string) => s.scopes_kpi.find((k) => k.scope === name)
  const change = (v: number | null, comparable: boolean) => (comparable && v != null
    ? `${v > 0 ? '▲' : '▼'} ${Math.abs(v)}%`
    : '—')
  const tone = (v: number | null, comparable: boolean) =>
    !comparable || v == null ? 'bg-slate-400/20' : v > 0 ? 'bg-rose-500/30' : 'bg-emerald-400/30'

  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-xl bg-gradient-to-br from-slate-700 to-slate-900 p-4 text-white shadow-sm">
          <div className="flex items-center justify-between text-xs/5 opacity-80">
            <span>{t('totalEmissions')}</span>
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${tone(s.comparison?.change_pct ?? null, s.comparison?.comparable ?? false)}`}>
              {change(s.comparison?.change_pct ?? null, s.comparison?.comparable ?? false)}
            </span>
          </div>
          <div className="mt-1 text-2xl font-bold tabular-nums">{fmtKg(s.total_kg_co2e)} <span className="text-xs font-normal opacity-80">kg</span></div>
          <div className="text-xs opacity-75">{fmtKg(s.total_t_co2e, 2)} {t('tCO2e')}</div>
          <div className="mt-1 text-[11px] opacity-60">
            {s.comparison?.comparable ? `${t('vs')} ${s.comparison.baseline_label}` : s.comparison ? t('noBaseline') : t('noComparison')}
          </div>
        </div>
        {(['Scope 1', 'Scope 2', 'Scope 3'] as const).map((sc, i) => {
          const k = kpiBy(sc)
          const accents = ['from-brand-600 to-brand-800', 'from-sky-500 to-sky-700', 'from-violet-500 to-violet-700']
          return (
            <div key={sc} className={`rounded-xl bg-gradient-to-br ${accents[i]} p-4 text-white shadow-sm`}>
              <div className="flex items-center justify-between text-xs/5 opacity-80">
                <span>{t(sc === 'Scope 1' ? 'scope1' : sc === 'Scope 2' ? 'scope2' : 'scope3')}</span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${tone(k?.change_pct ?? null, k?.comparable ?? false)}`}>
                  {change(k?.change_pct ?? null, k?.comparable ?? false)}
                </span>
              </div>
              <div className="mt-1 text-2xl font-bold tabular-nums">{fmtKg(k?.kg ?? '0')} <span className="text-xs font-normal opacity-80">kg</span></div>
              <div className="text-xs opacity-75">{(Number(k?.kg ?? 0) / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 })} t CO₂e</div>
              <div className="mt-1 text-[11px] opacity-80">{k?.share_pct == null ? '—' : `${k.share_pct}% ${t('ofTotal')}`}</div>
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
          <div className="text-xs text-slate-400">{t('records')}</div>
          <div className="text-lg font-bold tabular-nums">{s.calculated} / {s.records}</div>
          <div className="text-[11px] text-slate-400">{t('calculated')}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
          <div className="text-xs text-slate-400">{t('needsReview')}</div>
          <div className={`text-lg font-bold tabular-nums ${s.needs_review > 0 ? 'text-amber-600' : 'text-slate-700'}`}>{s.needs_review}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
          <div className="text-xs text-slate-400">{t('verifiedShare')}</div>
          <div className="text-lg font-bold tabular-nums">{s.verified_pct == null ? '—' : `${s.verified_pct.toFixed(1)}%`}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
          <div className="text-xs text-slate-400">{t('avgMonthly')}</div>
          <div className="text-lg font-bold tabular-nums">{s.avg_monthly_active_kg ? fmtKg(s.avg_monthly_active_kg) : '—'} <span className="text-xs font-normal">kg</span></div>
        </div>
      </div>
    </>
  )
}
