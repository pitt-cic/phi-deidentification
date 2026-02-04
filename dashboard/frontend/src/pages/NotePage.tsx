import { useParams, useSearchParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getNote, getNoteRedacted, getNoteAnnotations } from '../api/client'
import NoteViewer from '../components/NoteViewer'
import './NotePage.css'

interface NotePageProps {
  selectedEvalId: string | null
}

export default function NotePage({ selectedEvalId }: NotePageProps) {
  const { noteId } = useParams<{ noteId: string }>()
  const [searchParams] = useSearchParams()
  const highlightPosition = searchParams.get('highlight')
    ? parseInt(searchParams.get('highlight')!, 10)
    : undefined

  const { data: noteContent, isLoading: contentLoading } = useQuery({
    queryKey: ['note', noteId],
    queryFn: () => getNote(noteId!),
    enabled: !!noteId,
  })

  const { data: redactedContent } = useQuery({
    queryKey: ['note-redacted', noteId],
    queryFn: () => getNoteRedacted(noteId!),
    enabled: !!noteId,
  })

  const { data: annotations, isLoading: annotationsLoading } = useQuery({
    queryKey: ['annotations', noteId],
    queryFn: () => getNoteAnnotations(noteId!),
    enabled: !!noteId,
  })

  if (!noteId) {
    return (
      <div className="note-page">
        <div className="error-state">No note selected</div>
      </div>
    )
  }

  if (contentLoading || annotationsLoading) {
    return (
      <div className="note-page">
        <div className="loading-state">Loading note...</div>
      </div>
    )
  }

  if (!noteContent) {
    return (
      <div className="note-page">
        <div className="error-state">Failed to load note</div>
      </div>
    )
  }

  const stats = {
    tp: annotations?.spans.filter(s => s.classification === 'tp').length || 0,
    fp: annotations?.spans.filter(s => s.classification === 'fp').length || 0,
    fn: annotations?.spans.filter(s => s.classification === 'fn').length || 0,
  }

  return (
    <div className="note-page">
      <header className="page-header">
        <div className="breadcrumb">
          <Link to="/" className="breadcrumb-link">Overview</Link>
          <span className="breadcrumb-sep">/</span>
          <span className="breadcrumb-current">{noteId}</span>
        </div>
        <div className="note-stats">
          <span className="stat tp">{stats.tp} TP</span>
          <span className="stat fp">{stats.fp} FP</span>
          <span className="stat fn">{stats.fn} FN</span>
        </div>
      </header>

      <NoteViewer
        noteId={noteId}
        text={noteContent.text}
        redactedText={redactedContent?.text}
        spans={annotations?.spans || []}
        highlightPosition={highlightPosition}
      />
    </div>
  )
}
