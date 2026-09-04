import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'

const RouterContext = createContext(null)

/**
 * Clean browser-native Router provider supporting standard HTML5 History API.
 */
export function BrowserRouter({ children }) {
  const [pathname, setPathname] = useState(() => {
    if (typeof window !== 'undefined') {
      return window.location.pathname || '/'
    }
    return '/'
  })

  useEffect(() => {
    const handlePopState = () => {
      setPathname(window.location.pathname || '/')
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const navigate = useCallback((to, options = {}) => {
    if (typeof window === 'undefined') return
    const targetPath = typeof to === 'string' ? to : '/'
    if (options.replace) {
      window.history.replaceState(null, '', targetPath)
    } else {
      window.history.pushState(null, '', targetPath)
    }
    setPathname(targetPath)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  const value = useMemo(
    () => ({
      pathname,
      navigate,
    }),
    [pathname, navigate]
  )

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

/**
 * Hook to programmatic navigation.
 * Usage: const navigate = useNavigate(); navigate('/results');
 */
export function useNavigate() {
  const context = useContext(RouterContext)
  if (!context) {
    return (to) => {
      if (typeof window !== 'undefined') {
        window.location.href = to
      }
    }
  }
  return context.navigate
}

/**
 * Hook to access current route location.
 */
export function useLocation() {
  const context = useContext(RouterContext)
  return {
    pathname: context ? context.pathname : typeof window !== 'undefined' ? window.location.pathname : '/',
  }
}

/**
 * Routes container component.
 */
export function Routes({ children }) {
  const { pathname } = useLocation()
  let matchedElement = null

  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) return
    const { path, element } = child.props
    if (path === pathname || (path === '*' && !matchedElement)) {
      matchedElement = element
    }
  })

  return matchedElement
}

/**
 * Route declaration component.
 */
export function Route({ path, element }) {
  return element
}

/**
 * Link navigation component.
 */
export function Link({ to, children, className = '', ...rest }) {
  const navigate = useNavigate()

  const handleClick = (e) => {
    e.preventDefault()
    navigate(to)
  }

  return (
    <a href={to} onClick={handleClick} className={className} {...rest}>
      {children}
    </a>
  )
}
