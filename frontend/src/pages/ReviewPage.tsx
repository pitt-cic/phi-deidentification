import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useInfiniteQuery, useQuery, useMutation, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { listNotes, getNote, approveNote, type Note, type Batch, type PaginatedResponse } from '../api/client'
import DiffViewer from '../components/DiffViewer'
import './ReviewPage.css'

const PAGE_SIZE = 50
type BatchesQueryData = InfiniteData<PaginatedResponse<Batch>, number>

const normalizeRedactedForComparison = (value: string): string => value.replace(/\r\n/g, '\n')

export default function ReviewPage() {
  const { batchId, noteId } = useParams<{ batchId: string; noteId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editableRedactedText, setEditableRedactedText] = useState('')
  const [isEditingRedacted, setIsEditingRedacted] = useState(false)

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

  useEffect(() => {
    setEditableRedactedText(noteDetail?.redacted_text ?? '')
    setIsEditingRedacted(false)
  }, [noteDetail?.note_id, noteDetail?.redacted_text])

  const approveMutation = useMutation({
    mutationFn: ({ approved, redacted_text }: { approved: boolean; redacted_text?: string }) =>
      approveNote(batchId!, selectedNoteId!, { approved, redacted_text }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['notes', batchId] })
      queryClient.invalidateQueries({ queryKey: ['note-detail', batchId, selectedNoteId] })
      queryClient.invalidateQueries({ queryKey: ['batches'] })
      queryClient.invalidateQueries({ queryKey: ['batch', batchId] })

      if (variables.approved === false && batchId) {
        queryClient.setQueryData<BatchesQueryData>(['batches'], (current) => {
          if (!current) return current
          return {
            ...current,
            pages: current.pages.map((page) => ({
              ...page,
              items: page.items.map((batch) => (
                batch.batch_id === batchId ? { ...batch, all_approved: false } : batch
              )),
            })),
          }
        })
      }
    },
  })

  const goToNote = (id: string) => navigate(`/review/${batchId}/${id}`)
  const currentIdx = notes.findIndex(n => n.note_id === selectedNoteId)
  const hasPrev = currentIdx > 0
  const hasNext = currentIdx < notes.length - 1
  const hasRedactedEdits = !!noteDetail && (
    normalizeRedactedForComparison(editableRedactedText)
    !== normalizeRedactedForComparison(noteDetail.redacted_text)
  )
  const canShowDiff =
    !!noteDetail
    && !!noteDetail.original_text
    && (
      editableRedactedText.length > 0
      || (noteDetail.output_redacted_text ?? '').length > 0
      || noteDetail.redacted_text.length > 0
    )

  const handleSaveRedacted = () => {
    if (!noteDetail || !noteDetail.approved || !hasRedactedEdits || approveMutation.isPending) return
    approveMutation.mutate(
      {
        approved: noteDetail.approved,
        redacted_text: editableRedactedText,
      },
      {
        onSuccess: () => {
          setIsEditingRedacted(false)
        },
      },
    )
  }

  if (!batchId) {
    return <div className="review-page"><div className="error-state">No batch selected</div></div>
  }

  return (
    <div className="review-page">
      <aside className="review-sidebar">
        <div className="sidebar-header">
          <Link to={`/?batch=${encodeURIComponent(batchId)}`} className="back-link">&larr; Back to Dashboard</Link>
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
                    {note.approved ? (
                      <span className="badge badge-approved">Approved</span>
                    ) : note.has_output ? (
                      <span className="badge badge-ready">Ready</span>
                    ) : (
                      <span className="badge badge-pending">Pending</span>
                    )}
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
                {noteDetail.approved ? (
                  <button
                    className="btn btn-sm btn-danger"
                    onClick={() => approveMutation.mutate({
                      approved: false,
                      redacted_text: editableRedactedText,
                    })}
                    disabled={approveMutation.isPending}
                  >
                    Revoke Approval
                  </button>
                ) : (
                  <button
                    className="btn btn-sm btn-approve"
                    onClick={() => approveMutation.mutate({
                      approved: true,
                      redacted_text: editableRedactedText,
                    })}
                    disabled={approveMutation.isPending}
                  >
                    Save &amp; Approve
                  </button>
                )}
              </div>
            </div>

            <div className="review-content">
              {canShowDiff ? (
                <DiffViewer
                  original={noteDetail.original_text}
                  redacted={editableRedactedText}
                  editableRedacted={isEditingRedacted}
                  onRedactedChange={setEditableRedactedText}
                  onToggleEditRedacted={() => setIsEditingRedacted(true)}
                  editToggleDisabled={approveMutation.isPending}
                  onSaveRedacted={handleSaveRedacted}
                  saveDisabled={approveMutation.isPending || !hasRedactedEdits || !noteDetail.approved}
                  saveLabel={approveMutation.isPending ? 'Saving...' : 'Save'}
                />
              ) : (
                <div className="empty-state">
                  {noteDetail.original_text ? 'Redacted output not yet available.' : 'Original text not available'}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
