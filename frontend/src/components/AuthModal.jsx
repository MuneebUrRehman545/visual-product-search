import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'

export default function AuthModal({ isOpen, initialMode = 'login', onClose }) {
  const { login, signup, demoLogin } = useAuth()
  const [mode, setMode] = useState(initialMode) // 'login' | 'signup'
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  if (!isOpen) return null

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      if (mode === 'signup') {
        if (!username.trim()) {
          throw new Error('Please enter your name.')
        }
        await signup(email, username, password)
      } else {
        await login(email, password)
      }
      onClose()
    } catch (err) {
      setError(err.message || 'Authentication failed. Please check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  const handleDemoLogin = async () => {
    setError(null)
    setLoading(true)
    try {
      await demoLogin()
      onClose()
    } catch (err) {
      setError(err.message || 'Demo login failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="auth-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Close Button */}
        <button className="modal-close-btn" onClick={onClose} aria-label="Close modal">
          &times;
        </button>

        {/* Modal Header */}
        <div className="auth-header">
          <div className="auth-logo-badge">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
              <path d="M2 17l10 5 10-5"></path>
              <path d="M2 12l10 5 10-5"></path>
            </svg>
          </div>
          <h2>{mode === 'signup' ? 'Create Account' : 'Welcome Back'}</h2>
          <p className="auth-subtitle">
            {mode === 'signup'
              ? 'Join to save searches and explore 44,000+ fashion products'
              : 'Sign in to access your visual search workspace'}
          </p>
        </div>

        {/* 1-Click Demo Login Banner */}
        <div className="demo-login-box">
          <div className="demo-info">
            <span className="demo-tag">⚡ Fast Access</span>
            <span className="demo-desc">Want to test the app instantly?</span>
          </div>
          <button
            type="button"
            className="btn-demo-action"
            onClick={handleDemoLogin}
            disabled={loading}
          >
            {loading ? 'Activating...' : '1-Click Demo Login'}
          </button>
        </div>

        <div className="auth-divider">
          <span>or continue with email</span>
        </div>

        {/* Mode Switch Tabs */}
        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
            onClick={() => {
              setMode('login')
              setError(null)
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            className={`auth-tab ${mode === 'signup' ? 'active' : ''}`}
            onClick={() => {
              setMode('signup')
              setError(null)
            }}
          >
            Create Account
          </button>
        </div>

        {/* Error Notice */}
        {error && (
          <div className="auth-error-banner" role="alert">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="auth-form">
          {mode === 'signup' && (
            <div className="form-group">
              <label htmlFor="auth-username">Full Name</label>
              <div className="input-wrapper">
                <svg className="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                  <circle cx="12" cy="7" r="4"></circle>
                </svg>
                <input
                  id="auth-username"
                  type="text"
                  placeholder="e.g. Alex Johnson"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </div>
            </div>
          )}

          <div className="form-group">
            <label htmlFor="auth-email">Email Address</label>
            <div className="input-wrapper">
              <svg className="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
                <polyline points="22,6 12,13 2,6"></polyline>
              </svg>
              <input
                id="auth-email"
                type="email"
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="auth-password">Password</label>
            <div className="input-wrapper">
              <svg className="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
              </svg>
              <input
                id="auth-password"
                type={showPassword ? 'text' : 'password'}
                placeholder={mode === 'signup' ? 'Min 6 characters' : 'Enter your password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button
                type="button"
                className="pwd-toggle-btn"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          <button type="submit" className="btn-auth-submit" disabled={loading}>
            {loading ? (
              <span className="spinner-inline"></span>
            ) : mode === 'signup' ? (
              'Create Account'
            ) : (
              'Sign In'
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
