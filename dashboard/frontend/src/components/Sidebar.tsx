import { useQuery } from '@tanstack/react-query'
import { Link, useLocation } from 'react-router-dom'
import { listEvaluations, listNotes } from '../api/client'
import ThemeToggle from './ThemeToggle'
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

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <Link to="/" className="sidebar-logo">
          <span className="logo-icon">◈</span>
          <span className="logo-text">PII Dashboard</span>
        </Link>
        <ThemeToggle />
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
            {notes?.map(note => (
              <Link
                key={note.note_id}
                to={`/note/${note.note_id}`}
                className={`note-item ${note.has_mistakes ? 'has-mistakes' : ''} ${
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
    </aside>
  )
}
