import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Button, Input, Modal } from '../components/ui'
import { api, errMsg } from '../api/client'
import { useI18n } from '../i18n'

export default function Login() {
  const { login, user, refresh } = useAuth()
  const { t, lang, setLang } = useI18n()
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [showForce, setShowForce] = useState(false)
  const [oldPw, setOldPw] = useState(password)
  const [newPw, setNewPw] = useState('')
  const [pwMsg, setPwMsg] = useState('')

  if (user && !showForce) nav('/')

  const submit = async () => {
    setErr(''); setBusy(true)
    try {
      await login(username, password)
      const me = await api.get('/auth/me')
      if (me.data.must_change_password) setShowForce(true)
      else nav('/')
    } catch (e) {
      setErr(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const doChange = async () => {
    setPwMsg('')
    try {
      await api.post('/auth/change-password', { old_password: oldPw, new_password: newPw })
      await refresh()
      setShowForce(false)
      nav('/')
    } catch (e) {
      setPwMsg(errMsg(e))
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-brand-950 to-slate-900 p-4">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="text-5xl">🌿</div>
          <h1 className="mt-2 text-2xl font-bold text-white">CarbonAI</h1>
          <p className="text-sm text-brand-200/80">{t('tagline')}</p>
        </div>
        <div className="rounded-2xl bg-white p-6 shadow-2xl">
          {err && <div className="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-inset ring-rose-600/20">{err}</div>}
          <form onSubmit={(e) => { e.preventDefault(); submit() }} className="space-y-3">
            <Input label={t('username')} value={username} onChange={setUsername} required />
            <Input label={t('password')} value={password} onChange={setPassword} type="password" required />
            <Button type="submit" className="w-full" disabled={busy}>{busy ? '…' : t('login')}</Button>
          </form>
          <div className="mt-4 flex items-center justify-between text-xs text-slate-400">
            <button onClick={() => setLang(lang === 'ar' ? 'en' : 'ar')} className="hover:text-slate-600">
              {lang === 'ar' ? 'English' : 'العربية'}
            </button>
            <span>v2.0</span>
          </div>
        </div>
      </div>

      <Modal open={showForce} title={t('mustChange')} onClose={() => {}}>
        <div className="space-y-3">
          {pwMsg && <div className="rounded bg-rose-50 px-3 py-2 text-sm text-rose-700">{pwMsg}</div>}
          <Input label={t('currentPassword')} value={oldPw} onChange={setOldPw} type="password" />
          <Input label={t('newPassword')} value={newPw} onChange={setNewPw} type="password" />
          <Button onClick={doChange} className="w-full">{t('changePassword')}</Button>
        </div>
      </Modal>
    </div>
  )
}
