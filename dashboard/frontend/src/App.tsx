import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useState } from 'react'
import Sidebar from './components/Sidebar'
import HomePage from './pages/HomePage'
import NotePage from './pages/NotePage'
import './App.css'

function App() {
  const [selectedEvalId, setSelectedEvalId] = useState<string | null>(null)

  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar 
          selectedEvalId={selectedEvalId} 
          onEvalChange={setSelectedEvalId} 
        />
        <main className="main-content">
          <Routes>
            <Route 
              path="/" 
              element={<HomePage selectedEvalId={selectedEvalId} />} 
            />
            <Route 
              path="/note/:noteId" 
              element={<NotePage selectedEvalId={selectedEvalId} />} 
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App



