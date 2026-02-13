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

function App() {
  return (
    <ThemeProvider>
      <Authenticator>
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
