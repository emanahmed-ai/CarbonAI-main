import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Layout from './components/Layout'
import { I18nProvider } from './i18n'
import Consolidated from './pages/Consolidated'
import Dashboard from './pages/Dashboard'
import Factors from './pages/Factors'
import ImportPage from './pages/ImportPage'
import Invoices from './pages/Invoices'
import Login from './pages/Login'
import MLPage from './pages/MLPage'
import Organization from './pages/Organization'
import Plans from './pages/Plans'
import References from './pages/References'
import RecordNew from './pages/RecordNew'
import Records from './pages/Records'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Submissions from './pages/Submissions'
import Users from './pages/Users'

function RequireAdmin({ children }: { children: JSX.Element }) {
  const { user } = useAuth()
  if (user && user.role !== 'admin') return <Navigate to="/" replace />
  return children
}

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user } = useAuth()
  if (user === null && !localStorage.getItem('carbonai.token')) return <Navigate to="/login" replace />
  if (user === null) return <div className="p-8 text-sm text-slate-400">…</div>
  return children
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<RequireAuth><Layout /></RequireAuth>}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/records" element={<Records />} />
              <Route path="/records/new" element={<RecordNew />} />
              <Route path="/submissions" element={<Submissions />} />
              <Route path="/consolidated" element={<Consolidated />} />
              <Route path="/factors" element={<RequireAdmin><Factors /></RequireAdmin>} />
              <Route path="/import" element={<ImportPage />} />
              <Route path="/invoices" element={<Invoices />} />
              <Route path="/references" element={<References />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/plans" element={<Plans />} />
              <Route path="/organization" element={<Organization />} />
              <Route path="/users" element={<Users />} />
              <Route path="/ml" element={<MLPage />} />
              <Route path="/settings" element={<Settings />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  )
}
