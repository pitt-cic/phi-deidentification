import { useParams, useNavigate, Link } from 'react-router-dom'
import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listNotes, getNote, approveNote, getDownloadUrl, type Note } from '../api/client'
import DiffViewer from '../components/DiffViewer'
import './ReviewPage.css'

const PAGE_SIZE = 50

export default function ReviewPage() {
  const { batchId, noteId } = useParams<{ batchId: string; noteId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const {
    data: notePages,
    isLoading: notesLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['notes', batchId],
    queryFn: ({ pageParam = 0 }) => listNotes(batchId!, PAGE_SIZE, pageParam),
    getNextPageParam: (lastPage) => {
      const next = lastPage.offset + lastPage.limit
      return next < lastPage.total ? next : undefined
    },
    initialPageParam: 0,
    enabled: !!batchId,
  })

  const notes = notePages?.pages.flatMap(p => p.items) ?? []
  const totalNotes = notePages?.pages[0]?.total ?? 0

  const selectedNoteId = noteId || notes[0]?.note_id

  const { data: noteDetail, isLoading: noteLoading } = useQuery({
    queryKey: ['note-detail', batchId, selectedNoteId],
    queryFn: () => getNote(batchId!, selectedNoteId!),
    enabled: !!batchId && !!selectedNoteId,
  })

  const approveMutation = useMutation({
    mutationFn: ({ approved }: { approved: boolean }) =>
      approveNote(batchId!, selectedNoteId!, approved),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes', batchId] })
      queryClient.invalidateQueries({ queryKey: ['note-detail', batchId, selectedNoteId] })
    },
  })

  const handleDownload = async () => {
    if (!batchId || !selectedNoteId) return
    try {
      const { download_url } = await getDownloadUrl(batchId, selectedNoteId)
      window.open(download_url, '_blank')
    } catch (err) {
      alert(`Download error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    }
  }

  const goToNote = (id: string) => navigate(`/review/${batchId}/${id}`)
  const currentIdx = notes.findIndex(n => n.note_id === selectedNoteId)
  const hasPrev = currentIdx > 0
  const hasNext = currentIdx < notes.length - 1

  if (!batchId) {
    return <div className="review-page"><div className="error-state">No batch selected</div></div>
  }

  return (
    <div className="review-page">
      <aside className="review-sidebar">
        <div className="sidebar-header">
          <Link to="/" className="back-link">&larr; Dashboard</Link>
          <h3 className="sidebar-title">{batchId}</h3>
          <span className="note-count">{totalNotes > 0 ? `${totalNotes} notes` : '...'}</span>
        </div>
        <div className="notes-list">
          {notesLoading ? (
            <div className="loading-state">Loading...</div>
          ) : (
            <>
              {notes.map((note: Note) => (
                <button
                  key={note.note_id}
                  className={`note-item ${note.note_id === selectedNoteId ? 'active' : ''} ${note.approved ? 'approved' : ''}`}
                  onClick={() => goToNote(note.note_id)}
                >
                  <span className="note-item-name">{note.note_id}</span>
                  <span className="note-item-badges">
                    {note.has_output
                      ? <span className="badge badge-ready">Ready</span>
                      : <span className="badge badge-pending">Pending</span>}
                    {note.approved && <span className="badge badge-approved">Approved</span>}
                  </span>
                </button>
              ))}
              {hasNextPage && (
                <button
                  className="note-item load-more-notes"
                  onClick={() => fetchNextPage()}
                  disabled={isFetchingNextPage}
                >
                  {isFetchingNextPage ? 'Loading...' : `Load more (${notes.length} of ${totalNotes})`}
                </button>
              )}
            </>
          )}
        </div>
      </aside>

      <div className="review-main">
        {!selectedNoteId ? (
          <div className="empty-state">Select a note from the sidebar</div>
        ) : noteLoading ? (
          <div className="loading-state">Loading note...</div>
        ) : !noteDetail ? (
          <div className="error-state">Failed to load note</div>
        ) : (
          <>
            <div className="review-toolbar">
              <div className="toolbar-left">
                <button className="btn btn-sm" onClick={() => hasPrev && goToNote(notes[currentIdx - 1].note_id)} disabled={!hasPrev}>
                  &larr; Prev
                </button>
                <span className="toolbar-note-name">{selectedNoteId}</span>
                <button className="btn btn-sm" onClick={() => hasNext && goToNote(notes[currentIdx + 1].note_id)} disabled={!hasNext}>
                  Next &rarr;
                </button>
                <span className="toolbar-position">{currentIdx + 1} of {totalNotes}</span>
              </div>
              <div className="toolbar-right">
                {noteDetail.needs_review && <span className="review-flag">Needs Review</span>}
                <button className="btn btn-sm" onClick={handleDownload}>Download</button>
                {noteDetail.approved ? (
                  <button className="btn btn-sm btn-danger" onClick={() => approveMutation.mutate({ approved: false })} disabled={approveMutation.isPending}>
                    Revoke Approval
                  </button>
                ) : (
                  <button className="btn btn-sm btn-approve" onClick={() => approveMutation.mutate({ approved: true })} disabled={approveMutation.isPending}>
                    Approve
                  </button>
                )}
              </div>
            </div>

            <div className="review-content">
              {noteDetail.original_text && noteDetail.redacted_text ? (
                <DiffViewer original={noteDetail.original_text} redacted={noteDetail.redacted_text} />
              ) : (
                <div className="empty-state">
                  {noteDetail.redacted_text ? 'Original text not available' : 'Redacted output not yet available.'}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
