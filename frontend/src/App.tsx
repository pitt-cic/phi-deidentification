/**
 * Main application component with authentication and routing.
 * Provides Cognito authentication flow and application layout.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import { confirmResetPassword, resetPassword } from 'aws-amplify/auth'
import { Authenticator } from '@aws-amplify/ui-react'
import { ThemeProvider } from './contexts/ThemeContext'
import ThemeToggle from './components/ThemeToggle'
import DashboardPage from './pages/DashboardPage'
import ReviewPage from './pages/ReviewPage'
import '@aws-amplify/ui-react/styles.css'
import './App.css'

type AuthToast = {
  id: number
  message: string
  tone: 'info' | 'success'
}

/** Application header with navigation and user controls */
function Header({ signOut, username }: { signOut: () => void; username: string }) {
  const displayName = username || 'unknown'

  return (
    <header className="app-header">
      <Link to="/" className="header-logo">
        <span className="logo-icon">◈</span>
        <span className="logo-text">PII De-identification</span>
      </Link>
      <div className="header-right">
        <span className="user-info">Logged in as: {displayName}</span>
        <ThemeToggle />
        <button className="sign-out-btn" onClick={signOut}>
          Sign Out
        </button>
      </div>
    </header>
  )
}

/** Toast notification display for authentication status messages */
function AuthStatusToasts({ toasts }: { toasts: AuthToast[] }) {
  if (toasts.length === 0) return null

  return (
    <div className="auth-toast-stack" aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <div key={toast.id} className={`auth-toast auth-toast-${toast.tone}`} role="status">
          {toast.message}
        </div>
      ))}
    </div>
  )
}

/** Root application component with authentication and routing */
function App() {
  const [authToasts, setAuthToasts] = useState<AuthToast[]>([])
  const timeoutIdsRef = useRef<Array<ReturnType<typeof window.setTimeout>>>([])

  const pushAuthToast = useCallback((message: string, tone: AuthToast['tone']) => {
    const id = Date.now() + Math.random()
    setAuthToasts((current) => [...current, { id, message, tone }])

    const timeoutId = window.setTimeout(() => {
      setAuthToasts((current) => current.filter((toast) => toast.id !== id))
      timeoutIdsRef.current = timeoutIdsRef.current.filter((existingId) => existingId !== timeoutId)
    }, 4000)

    timeoutIdsRef.current.push(timeoutId)
  }, [])

  useEffect(() => {
    return () => {
      timeoutIdsRef.current.forEach((timeoutId) => window.clearTimeout(timeoutId))
      timeoutIdsRef.current = []
    }
  }, [])

  const authServices = {
    async handleForgotPassword(input: Parameters<typeof resetPassword>[0]) {
      const result = await resetPassword(input)
      pushAuthToast('Verification code sent. Check your email for the reset code.', 'info')
      return result
    },
    async handleForgotPasswordSubmit(input: Parameters<typeof confirmResetPassword>[0]) {
      const result = await confirmResetPassword(input)
      pushAuthToast('Password reset successful. You can now sign in with your new password.', 'success')
      return result
    },
  }

  const authComponents = {
    Header() {
      return (
        <div className="auth-header">
          <AuthStatusToasts toasts={authToasts} />
          <div className="auth-header-toggle">
            <ThemeToggle />
          </div>
          <div className="auth-brand">
            <span className="logo-icon auth-brand-icon">◈</span>
            <div className="auth-brand-text">
              <h1 className="auth-title">PII De-identification</h1>
              <p className="auth-subtitle">Sign in to review and approve redacted notes</p>
            </div>
          </div>
        </div>
      )
    },
    Footer() {
      return (
        <div className="auth-footer">
          <p className="auth-footer-note">
            Need an account? Ask your administrator to create and invite your user.
          </p>
          <p className="auth-footer-note">
            Use the temporary password from your invite email to sign in, then set a new password.
          </p>
          <p className="auth-footer-meta">Protected access provided through Amazon Cognito.</p>
        </div>
      )
    },
  }

  return (
    <ThemeProvider>
      <Authenticator components={authComponents} services={authServices} hideSignUp>
        {({ signOut, user }) => (
          <BrowserRouter>
            <div className="app-layout">
              <Header
                signOut={signOut!}
                username={user?.signInDetails?.loginId || user?.username || ''}
              />
              <main className="main-content">
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/review/:batchId" element={<ReviewPage />} />
                  <Route path="/review/:batchId/:noteId" element={<ReviewPage />} />
                </Routes>
              </main>
            </div>
          </BrowserRouter>
        )}
      </Authenticator>
    </ThemeProvider>
  )
}

export default App
