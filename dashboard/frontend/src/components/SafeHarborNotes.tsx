import { useQuery } from '@tanstack/react-query'
import { listSafeHarborNotes, getSafeHarborComparison } from '../api/client'
import { useState } from 'react'
import ThreePanelDiff from './ThreePanelDiff'
import './SafeHarborNotes.css'

export default function SafeHarborNotes() {
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null)
  
  const { data: notes, isLoading: notesLoading } = useQuery({
    queryKey: ['safe-harbor-notes'],
    queryFn: listSafeHarborNotes,
  })

  const { data: comparison, isLoading: comparisonLoading } = useQuery({
    queryKey: ['safe-harbor-comparison', selectedNoteId],
    queryFn: () => getSafeHarborComparison(selectedNoteId!),
    enabled: !!selectedNoteId,
  })

  if (notesLoading) {
    return (
      <div className="safe-harbor-notes">
        <div className="loading-state">Loading Safe Harbor Notes...</div>
      </div>
    )
  }

  if (!notes || notes.length === 0) {
    return (
      <div className="safe-harbor-notes">
        <div className="empty-state-large">
          <div className="empty-icon">📋</div>
          <h2>No Safe Harbor Notes Found</h2>
          <p>No redacted files found in sample-output-text directory.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="safe-harbor-notes">
      <header className="page-header">
        <h1 className="page-title">Safe Harbor Notes Comparison</h1>
      </header>

      <div className="safe-harbor-layout">
        <div className="notes-sidebar">
          <h2>Notes</h2>
          <div className="notes-list">
            {notes.map((note) => (
              <button
                key={note.note_id}
                className={`note-item ${selectedNoteId === note.note_id ? 'active' : ''}`}
                onClick={() => setSelectedNoteId(note.note_id)}
              >
                {note.note_id}
              </button>
            ))}
          </div>
        </div>

        <div className="comparison-view">
          {!selectedNoteId ? (
            <div className="empty-state">
              <p>Select a note to view comparison</p>
            </div>
          ) : comparisonLoading ? (
            <div className="loading-state">Loading comparison...</div>
          ) : !comparison ? (
            <div className="error-state">Failed to load comparison</div>
          ) : (
            <div className="comparison-content">
              <div className="comparison-header">
                <h2>{comparison.note_id}</h2>
              </div>

              <div className="diff-viewer-container">
                <ThreePanelDiff
                  original={comparison.original_text}
                  llmOutput={comparison.redacted_text}
                  groundTruth={comparison.deid_text}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
