import React, { createContext, useContext, useState, useEffect } from 'react'
import { getApiBaseUrl } from '../services/searchApi'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(null)
  const [loading, setLoading] = useState(true)

  // Initialize auth state from localStorage on mount
  useEffect(() => {
    const savedToken = localStorage.getItem('vps_auth_token')
    const savedUser = localStorage.getItem('vps_auth_user')

    if (savedToken && savedUser) {
      try {
        setToken(savedToken)
        setUser(JSON.parse(savedUser))
      } catch (err) {
        localStorage.removeItem('vps_auth_token')
        localStorage.removeItem('vps_auth_user')
      }
    }
    setLoading(false)
  }, [])

  const login = async (email, password) => {
    const baseUrl = getApiBaseUrl()
    const res = await fetch(`${baseUrl}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })

    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || 'Login failed.')
    }

    setToken(data.token)
    setUser(data.user)
    localStorage.setItem('vps_auth_token', data.token)
    localStorage.setItem('vps_auth_user', JSON.stringify(data.user))
    return data.user
  }

  const signup = async (email, username, password) => {
    const baseUrl = getApiBaseUrl()
    const res = await fetch(`${baseUrl}/api/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, username, password }),
    })

    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || 'Signup failed.')
    }

    setToken(data.token)
    setUser(data.user)
    localStorage.setItem('vps_auth_token', data.token)
    localStorage.setItem('vps_auth_user', JSON.stringify(data.user))
    return data.user
  }

  const demoLogin = async () => {
    const baseUrl = getApiBaseUrl()
    const res = await fetch(`${baseUrl}/api/auth/demo`)
    const data = await res.json()

    if (!res.ok) {
      throw new Error(data.detail || 'Demo login failed.')
    }

    setToken(data.token)
    setUser(data.user)
    localStorage.setItem('vps_auth_token', data.token)
    localStorage.setItem('vps_auth_user', JSON.stringify(data.user))
    return data.user
  }

  const logout = () => {
    setToken(null)
    setUser(null)
    localStorage.removeItem('vps_auth_token')
    localStorage.removeItem('vps_auth_user')
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token,
        loading,
        login,
        signup,
        demoLogin,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
