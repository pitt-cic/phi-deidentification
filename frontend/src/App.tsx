import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import { Authenticator } from '@aws-amplify/ui-react'
import { ThemeProvider } from './contexts/ThemeContext'
import ThemeToggle from './components/ThemeToggle'
import DashboardPage from './pages/DashboardPage'
import ReviewPage from './pages/ReviewPage'
import '@aws-amplify/ui-react/styles.css'
import './App.css'

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

const authComponents = {
  Header() {
    return (
      <div className="auth-header">
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

function App() {
  return (
    <ThemeProvider>
      <Authenticator components={authComponents} hideSignUp>
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
