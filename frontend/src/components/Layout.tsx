import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useI18n } from '../i18n'
import type { DictKey } from '../i18n'

type NavItem = { to: string; key: DictKey; icon: string; roles: string[] }

const NAV: { group: DictKey; items: NavItem[] }[] = [
  {
    group: 'groupOperations',
    items: [
      { to: '/', key: 'navDashboard', icon: '📊', roles: ['admin', 'head_office', 'factory_manager', 'viewer'] },
      { to: '/records/new', key: 'navNewRecord', icon: '➕', roles: ['admin', 'head_office', 'factory_manager'] },
      { to: '/records', key: 'navRecords', icon: '📋', roles: ['admin', 'head_office', 'factory_manager', 'viewer'] },
      { to: '/import', key: 'navImport', icon: '📥', roles: ['admin', 'head_office', 'factory_manager'] },
      { to: '/invoices', key: 'navInvoices', icon: '🧾', roles: ['admin', 'head_office', 'factory_manager'] },
    ],
  },
  {
    group: 'groupAnalysis',
    items: [
      { to: '/submissions', key: 'navSubmissions', icon: '📨', roles: ['admin', 'head_office', 'factory_manager'] },
      { to: '/consolidated', key: 'navConsolidated', icon: '🏢', roles: ['admin', 'head_office'] },
      { to: '/factors', key: 'navFactors', icon: '📚', roles: ['admin'] },
      { to: '/references', key: 'navReferences', icon: '📜', roles: ['admin', 'head_office', 'factory_manager', 'viewer'] },
      { to: '/reports', key: 'navReports', icon: '🧾', roles: ['admin', 'head_office', 'factory_manager', 'viewer'] },
      { to: '/plans', key: 'navPlans', icon: '🌱', roles: ['admin', 'head_office', 'factory_manager'] },
      { to: '/ml', key: 'navML', icon: '🤖', roles: ['admin', 'head_office', 'factory_manager', 'viewer'] },
    ],
  },
  {
    group: 'groupAdministration',
    items: [
      { to: '/organization', key: 'navOrganization', icon: '🏭', roles: ['admin', 'head_office'] },
      { to: '/users', key: 'navUsers', icon: '👥', roles: ['admin', 'head_office'] },
      { to: '/settings', key: 'navSettings', icon: '⚙️', roles: ['admin', 'head_office', 'factory_manager', 'viewer'] },
    ],
  },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const { t, lang, setLang } = useI18n()
  const loc = useLocation()
  const [open, setOpen] = useState(false)
  useEffect(() => setOpen(false), [loc.pathname])
  if (!user) return null
  const roleLabel = t(`roles.${user.role}` as DictKey)
  const facilityTag = user.role === 'factory_manager' || user.role === 'viewer'
  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-800">
      {/* sidebar */}
      <aside className={`fixed inset-y-0 z-40 w-64 shrink-0 flex-col bg-slate-900 text-slate-300 transition-transform lg:static lg:flex ${open ? 'flex translate-x-0' : 'hidden -translate-x-full'} rtl:translate-x-full lg:rtl:translate-x-0`}
        style={{ insetInlineStart: 0 }}>
        <div className="flex items-center gap-2 px-5 py-5">
          <span className="text-2xl">🌿</span>
          <div>
            <div className="font-bold text-white">CarbonAI</div>
            <div className="text-[10px] leading-3 opacity-60">{t('tagline')}</div>
          </div>
        </div>
        <nav className="flex-1 space-y-4 overflow-y-auto px-3 pb-6">
          {NAV.map((sec) => {
            const items = sec.items.filter((i) => i.roles.includes(user.role))
            if (!items.length) return null
            return (
              <div key={sec.group}>
                <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{t(sec.group)}</div>
                {items.map((i) => (
                  <NavLink key={i.to} to={i.to} end={i.to === '/'}
                    className={({ isActive }) =>
                      `mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${isActive ? 'bg-brand-600 font-medium text-white shadow' : 'hover:bg-slate-800 hover:text-white'}`}>
                    <span>{i.icon}</span>{t(i.key)}
                  </NavLink>
                ))}
              </div>
            )
          })}
        </nav>
        <div className="border-t border-slate-800 px-4 py-3 text-xs">
          <div className="font-medium text-white">{user.full_name || user.username}</div>
          <div className="opacity-60">{roleLabel}</div>
        </div>
      </aside>

      {/* main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur">
          <div className="flex items-center gap-3">
            <button className="rounded p-1.5 text-slate-500 hover:bg-slate-100 lg:hidden" onClick={() => setOpen(!open)}>☰</button>
            {facilityTag ? (
              <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-600/20">
                {t('facilityScope')} #{user.facility_id}
              </span>
            ) : (
              <span className="rounded-full bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700 ring-1 ring-inset ring-sky-600/20">
                {t('headOfficeView')}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
              {lang === 'ar' ? 'EN' : 'ع'}
            </button>
            <button onClick={logout} className="rounded-lg px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50">
              {t('logout')}
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 p-4 lg:p-6">
          <Outlet />
        </main>
        <footer className="px-6 pb-4 text-center text-[11px] text-slate-400">
          CarbonAI — لا تستخدم النتائج لاتخاذ قرارات رسمية قبل التحقق من عوامل الانبعاث والمصادر |
          Do not use results for official decisions before verifying factors and sources
        </footer>
      </div>
    </div>
  )
}
