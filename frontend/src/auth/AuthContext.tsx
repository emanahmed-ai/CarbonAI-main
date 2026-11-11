import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, setToken } from '../api/client'

export type User = {
  user_id: number
  username: string
  full_name?: string | null
  role: 'admin' | 'head_office' | 'factory_manager' | 'viewer'
  company_id: number | null
  facility_id: number | null
  locale: string
  must_change_password?: boolean
  last_login_at?: string | null
}

type Ctx = {
  user: User | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

const AuthContext = createContext<Ctx>({ user: null, login: async () => {}, logout: () => {}, refresh: async () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    if (getToken()) refresh()
  }, [])

  const refresh = async () => {
    try {
      const r = await api.get('/auth/me')
      setUser(r.data)
    } catch {
      setUser(null)
      setToken(null)
    }
  }

  const login = async (username: string, password: string) => {
    const r = await api.post('/auth/login', { username, password })
    setToken(r.data.token)
    setUser(r.data.user)
  }

  const logout = () => {
    setToken(null)
    setUser(null)
    window.location.href = '/login'
  }

  return <AuthContext.Provider value={{ user, login, logout, refresh }}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
