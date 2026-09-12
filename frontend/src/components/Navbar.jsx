import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { Link } from '../context/RouterContext'

export default function Navbar({ onOpenAuth, onResetSearch }) {
  const { user, isAuthenticated, logout } = useAuth()
  const [dropdownOpen, setDropdownOpen] = useState(false)

  return (
    <header className="navbar">
      <div className="navbar-container">
        {/* Brand / Logo */}
        <div className="navbar-brand" onClick={onResetSearch} role="button" tabIndex={0}>
          <div className="brand-icon-wrapper">
            <svg
              className="brand-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              <path d="M11 8v6"></path>
              <path d="M8 11h6"></path>
            </svg>
          </div>
          <div className="brand-text">
            <span className="brand-title">VisualSearch</span>
            <span className="brand-badge">AI Studio</span>
          </div>
        </div>

        {/* Live Catalog Status Pill */}
        <div className="catalog-status-pill">
          <span className="pulse-dot"></span>
          <span className="pill-text">44,119 Products Indexed</span>
          <span className="pill-model">OpenCLIP ViT-B/32</span>
        </div>

        <nav aria-label="Pipeline navigation">
          <Link to="/dashboard">Dashboard</Link>
          {' · '}
          <Link to="/rag">RAG</Link>
          {' · '}
          <Link to="/agent">Agent</Link>
        </nav>

        {/* User / Auth Actions */}
        <div className="navbar-actions">
          {isAuthenticated ? (
            <div className="user-profile-menu">
              <button
                className="user-profile-btn"
                onClick={() => setDropdownOpen(!dropdownOpen)}
                aria-label="User menu"
              >
                <div className="avatar-circle">
                  {user?.username ? user.username.charAt(0).toUpperCase() : 'U'}
                </div>
                <span className="user-name">{user?.username || 'User'}</span>
                <svg
                  className={`chevron-icon ${dropdownOpen ? 'rotate' : ''}`}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
              </button>

              {dropdownOpen && (
                <div className="dropdown-menu">
                  <div className="dropdown-header">
                    <p className="dropdown-user-name">{user?.username}</p>
                    <p className="dropdown-user-email">{user?.email}</p>
                  </div>
                  <div className="dropdown-divider"></div>
                  <button
                    className="dropdown-item logout-btn"
                    onClick={() => {
                      logout()
                      setDropdownOpen(false)
                    }}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                      <polyline points="16 17 21 12 16 7"></polyline>
                      <line x1="21" y1="12" x2="9" y2="12"></line>
                    </svg>
                    Sign Out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="auth-btn-group">
              <button
                className="btn-auth-signin"
                onClick={() => onOpenAuth('login')}
              >
                Sign In
              </button>
              <button
                className="btn-auth-signup"
                onClick={() => onOpenAuth('signup')}
              >
                Get Started
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
