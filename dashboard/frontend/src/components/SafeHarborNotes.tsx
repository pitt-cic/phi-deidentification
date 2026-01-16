import { useQuery } from '@tanstack/react-query'
import { listSafeHarborNotes, getSafeHarborComparison, getSafeHarborMetrics } from '../api/client'
import { useState } from 'react'
import './SafeHarborNotes.css'

function highlightPII(text: string, isGroundTruth: boolean = false): React.ReactNode[] {
  const bracketPattern = /\[[^\]]+\]/g
  const doubleStarPattern = /\*\*[^\s]+/g
  const matches: Array<{ start: number; end: number; type: 'bracket' | 'star' }> = []
  
  let match
  while ((match = bracketPattern.exec(text)) !== null) {
    matches.push({ start: match.index, end: match.index + match[0].length, type: 'bracket' })
  }
  
  while ((match = doubleStarPattern.exec(text)) !== null) {
    matches.push({ start: match.index, end: match.index + match[0].length, type: 'star' })
  }
  
  matches.sort((a, b) => a.start - b.start)
  
  const nonOverlapping: Array<{ start: number; end: number; type: 'bracket' | 'star' }> = []
  for (const match of matches) {
    const overlaps = nonOverlapping.some(m => 
      (match.start < m.end && match.end > m.start)
    )
    if (!overlaps) {
      nonOverlapping.push(match)
    }
  }
  
  const elements: React.ReactNode[] = []
  let lastIndex = 0
  
  for (const match of nonOverlapping) {
    if (match.start > lastIndex) {
      elements.push(text.substring(lastIndex, match.start))
    }
    
    const matchText = text.substring(match.start, match.end)
    const highlightClass = isGroundTruth && match.type === 'bracket' 
      ? 'pii-highlight star' 
      : `pii-highlight ${match.type}`
    elements.push(
      <span key={match.start} className={highlightClass}>
        {matchText}
      </span>
    )
    
    lastIndex = match.end
  }
  
  if (lastIndex < text.length) {
    elements.push(text.substring(lastIndex))
  }
  
  return elements.length > 0 ? elements : [text]
}

export default function SafeHarborNotes() {
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null)
  
  const { data: notes, isLoading: notesLoading } = useQuery({
    queryKey: ['safe-harbor-notes'],
    queryFn: listSafeHarborNotes,
  })

  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['safe-harbor-metrics'],
    queryFn: getSafeHarborMetrics,
  })

  const { data: comparison, isLoading: comparisonLoading } = useQuery({
    queryKey: ['safe-harbor-comparison', selectedNoteId],
    queryFn: () => getSafeHarborComparison(selectedNoteId!),
    enabled: !!selectedNoteId,
  })

  if (notesLoading || metricsLoading) {
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
        {metrics && (
          <div className="metrics-summary">
            <div className="metric-item">
              <span className="metric-label">Files:</span>
              <span className="metric-value">{metrics.total_files}</span>
            </div>
          </div>
        )}
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

              <div className="side-by-side-comparison">
                <div className="comparison-panel">
                  <h3>Redacted Text (LLM Output)</h3>
                  <div className="text-viewer">
                    {highlightPII(comparison.redacted_text, false)}
                  </div>
                </div>

                <div className="comparison-panel">
                  <h3>Ground Truth (DEID)</h3>
                  <div className="text-viewer ground-truth-viewer">
                    {highlightPII(comparison.deid_text, true)}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

