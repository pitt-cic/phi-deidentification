import { useQuery } from '@tanstack/react-query'
import { Link, useLocation } from 'react-router-dom'
import { listEvaluations, listNotes } from '../api/client'
import './Sidebar.css'

interface SidebarProps {
  selectedEvalId: string | null
  onEvalChange: (evalId: string | null) => void
}

export default function Sidebar({ selectedEvalId, onEvalChange }: SidebarProps) {
  const location = useLocation()
  
  const { data: evaluations, isLoading: evalsLoading } = useQuery({
    queryKey: ['evaluations'],
    queryFn: listEvaluations,
  })

  const { data: notes, isLoading: notesLoading } = useQuery({
    queryKey: ['notes', selectedEvalId],
    queryFn: () => listNotes(selectedEvalId || undefined),
    enabled: !!selectedEvalId,
  })

  if (evaluations && evaluations.length > 0 && !selectedEvalId) {
    onEvalChange(evaluations[0].eval_id)
  }

  const notesWithMistakes = notes?.filter(n => n.has_mistakes) || []
  const notesWithoutMistakes = notes?.filter(n => !n.has_mistakes) || []

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <Link to="/" className="sidebar-logo">
          <span className="logo-icon">◈</span>
          <span className="logo-text">PII Dashboard</span>
        </Link>
      </div>

      <div className="sidebar-section">
        <label className="section-label">Evaluation Run</label>
        <select 
          className="eval-selector"
          value={selectedEvalId || ''}
          onChange={(e) => onEvalChange(e.target.value || null)}
          disabled={evalsLoading}
        >
          {evalsLoading ? (
            <option>Loading...</option>
          ) : (
            evaluations?.map(ev => (
              <option key={ev.eval_id} value={ev.eval_id}>
                {ev.timestamp} (F1: {(ev.f1 * 100).toFixed(1)}%)
              </option>
            ))
          )}
        </select>
      </div>

      <nav className="sidebar-nav">
        <Link 
          to="/" 
          className={`nav-item ${location.pathname === '/' ? 'active' : ''}`}
        >
          <span className="nav-icon">📊</span>
          <span>Overview</span>
        </Link>
      </nav>

      <div className="sidebar-section notes-section">
        <label className="section-label">
          Notes
          {notes && <span className="count-badge">{notes.length}</span>}
        </label>
        
        {notesLoading ? (
          <div className="loading-text">Loading notes...</div>
        ) : (
          <div className="notes-list">
            {notesWithMistakes.length > 0 && (
              <div className="notes-group">
                <div className="group-label">
                  <span className="mistake-indicator">●</span>
                  With Mistakes ({notesWithMistakes.length})
                </div>
                {notesWithMistakes.map(note => (
                  <Link
                    key={note.note_id}
                    to={`/note/${note.note_id}`}
                    className={`note-item has-mistakes ${
                      location.pathname === `/note/${note.note_id}` ? 'active' : ''
                    }`}
                  >
                    <span className="note-id">{note.note_id}</span>
                    {note.note_type && (
                      <span className="note-type">{note.note_type}</span>
                    )}
                  </Link>
                ))}
              </div>
            )}
            
            {notesWithoutMistakes.length > 0 && (
              <div className="notes-group">
                <div className="group-label">
                  <span className="success-indicator">●</span>
                  Clean ({notesWithoutMistakes.length})
                </div>
                {notesWithoutMistakes.map(note => (
                  <Link
                    key={note.note_id}
                    to={`/note/${note.note_id}`}
                    className={`note-item ${
                      location.pathname === `/note/${note.note_id}` ? 'active' : ''
                    }`}
                  >
                    <span className="note-id">{note.note_id}</span>
                    {note.note_type && (
                      <span className="note-type">{note.note_type}</span>
                    )}
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  )
}
