import { createContext, useContext, useState, useEffect } from 'react'
import { login as apiLogin, logout as apiLogout } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('slm_user')) } catch { return null }
  })
  const [theme, setTheme] = useState(() => localStorage.getItem('slm_theme') || 'light')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  const login = async (email, password) => {
    setLoading(true)
    try {
      const data = await apiLogin(email, password)
      localStorage.setItem('slm_token', data.access_token)
      const u = { id: data.user_id, name: data.full_name, role: data.role }
      localStorage.setItem('slm_user', JSON.stringify(u))
      setUser(u)
      return u
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    try { await apiLogout() } catch {}
    localStorage.removeItem('slm_token')
    localStorage.removeItem('slm_user')
    setUser(null)
  }

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light'
    setTheme(newTheme)
    localStorage.setItem('slm_theme', newTheme)
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, loading, isAdmin: user?.role === 'Admin', theme, toggleTheme }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
