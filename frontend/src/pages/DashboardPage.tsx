import { useState, useEffect } from 'react'
import { useQuery, useInfiniteQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  listBatches,
  getBatch,
  startBatch,
  approveAllNotes,
  redriveBatch,
  type Batch,
  type PaginatedResponse,
} from '../api/client'
import './DashboardPage.css'

const PAGE_SIZE = 50

type BatchStatusKey =
  | 'created'
  | 'ready-to-process'
  | 'processing'
  | 'partially-completed'
  | 'needs-review'
  | 'approved'
  | 'unknown'

type BatchStatusDisplay = {
  key: BatchStatusKey
  label: string
}

type BatchesQueryData = InfiniteData<PaginatedResponse<Batch>, number>

const getBatchStatusDisplay = (status: Batch['status'], allApproved: boolean): BatchStatusDisplay => {
  if (status === 'completed') {
    return allApproved
      ? { key: 'approved', label: 'Approved' }
      : { key: 'needs-review', label: 'Needs Review' }
  }

  if (status === 'partially-completed') {
    return { key: 'partially-completed', label: 'Partially Completed' }
  }

  if (status === 'processing') {
    return { key: 'processing', label: 'Processing' }
  }

  if (status === 'ready') {
    return { key: 'ready-to-process', label: 'Ready to Process' }
  }

  if (status === 'created') {
    return { key: 'created', label: 'Created' }
  }

  return { key: 'unknown', label: 'Unknown' }
}

export default function DashboardPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(() => searchParams.get('batch'))
  const [startingBatchId, setStartingBatchId] = useState<string | null>(null)
  const [startError, setStartError] = useState('')
  const [approvingAll, setApprovingAll] = useState(false)
  const [retrying, setRetrying] = useState(false)

  useEffect(() => {
    const currentBatchParam = searchParams.get('batch')
    if (selectedBatchId === currentBatchParam) return

    const nextParams = new URLSearchParams(searchParams)
    if (selectedBatchId) {
      nextParams.set('batch', selectedBatchId)
    } else {
      nextParams.delete('batch')
    }
    setSearchParams(nextParams, { replace: true })
  }, [selectedBatchId, searchParams, setSearchParams])

  useEffect(() => {
    setStartError('')
  }, [selectedBatchId])

  const {
    data: batchPages,
    isLoading: batchesLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['batches'],
    queryFn: ({ pageParam = 0 }) => listBatches(PAGE_SIZE, pageParam),
    getNextPageParam: (lastPage) => {
      const next = lastPage.offset + lastPage.limit
      return next < lastPage.total ? next : undefined
    },
    initialPageParam: 0,
  })

  const batches = batchPages?.pages.flatMap(p => p.items) ?? []
  const totalBatches = batchPages?.pages[0]?.total ?? 0

  const { data: batchDetail } = useQuery({
    queryKey: ['batch', selectedBatchId],
    queryFn: () => getBatch(selectedBatchId!),
    enabled: !!selectedBatchId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'processing' ? 5_000 : false
    },
  })

  const createAndUploadCommand = `./scripts/create_batch.sh --notes-dir /PATH/TO/YOUR-NOTES`
  const uploadToExistingBatchCommandFor = (batchId: string) => {
    return `./scripts/create_batch.sh --batch-id "${batchId}" --notes-dir /PATH/TO/YOUR-NOTES`
  }

  const handleStartBatch = async (batchId: string) => {
    if (startingBatchId) return // Prevent double-submit
    setStartError('')
    setStartingBatchId(batchId)
    try {
      await startBatch(batchId)
      queryClient.invalidateQueries({ queryKey: ['batch', batchId] })
      queryClient.invalidateQueries({ queryKey: ['batches'] })
    } catch (err) {
      setStartError(err instanceof Error ? err.message : 'Failed to start batch')
    } finally {
      setStartingBatchId(null)
    }
  }

  const updateBatchApprovalBadge = (batchId: string, allApproved: boolean) => {
    queryClient.setQueryData<BatchesQueryData>(['batches'], (current) => {
      if (!current) return current
      return {
        ...current,
        pages: current.pages.map((page) => ({
          ...page,
          items: page.items.map((batch) => (
            batch.batch_id === batchId ? { ...batch, all_approved: allApproved } : batch
          )),
        })),
      }
    })
  }

  const handleApproveAll = async (batchId: string) => {
    setApprovingAll(true)
    try {
      const result = await approveAllNotes(batchId)

      queryClient.invalidateQueries({ queryKey: ['notes', batchId] })
      queryClient.invalidateQueries({ queryKey: ['note-detail', batchId] })
      queryClient.invalidateQueries({ queryKey: ['batch', batchId] })
      queryClient.invalidateQueries({ queryKey: ['batches'] })
      updateBatchApprovalBadge(batchId, result.all_approved)

      if (result.required_note_count === 0) {
        alert('No notes found in this batch.')
      } else if (result.all_approved) {
        alert(`Approved ${result.approved_note_count} notes.`)
      } else {
        alert(`Marked ${result.approved_note_count} notes approved. Batch processing must be completed first.`)
      }
    } catch (err) {
      alert(`Approve all error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setApprovingAll(false)
    }
  }

  const handleRetryFailedNotes = async (batchId: string) => {
    setRetrying(true)
    try {
      await redriveBatch(batchId)
      queryClient.invalidateQueries({ queryKey: ['batch', batchId] })
      queryClient.invalidateQueries({ queryKey: ['batches'] })
    } catch (err) {
      alert(`Retry failed: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setRetrying(false)
    }
  }

  const selectedBatchStatus = batchDetail
    ? getBatchStatusDisplay(batchDetail.status, !!batchDetail.all_approved)
    : null
  const canStartSelectedBatch = selectedBatchStatus?.key === 'ready-to-process' && !!selectedBatchId
  const isStartingSelectedBatch = !!selectedBatchId && startingBatchId === selectedBatchId
  const isCreatedBatch = batchDetail?.status === 'created'

  const piiStats = batchDetail?.pii_stats
  const piiTypeEntries = piiStats
    ? Object.entries(piiStats.by_type).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    : []
  const hasBreakdownData = piiTypeEntries.length > 0

  const formatEntityType = (entityType: string) =>
    entityType
      .toLowerCase()
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase())

  const formatTimestamp = (iso: string | undefined) => {
    if (!iso) return null
    return new Date(iso).toLocaleString()
  }

  return (
    <div className="dashboard-layout">
      <aside className="dashboard-sidebar">
        <div className="sidebar-section">
          <button
            className={`sidebar-item sidebar-item-new-batch ${!selectedBatchId ? 'active' : ''}`}
            onClick={() => setSelectedBatchId(null)}
          >
            <span>Dashboard</span>
          </button>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-label">Batches <span className="sidebar-count">{totalBatches}</span></div>
          <div className="sidebar-list">
            {batchesLoading ? (
              <div className="sidebar-empty">Loading...</div>
            ) : batches.length === 0 ? (
              <div className="sidebar-empty">No batches yet</div>
            ) : (
              <>
                {batches.map((batch: Batch) => {
                  const sidebarStatus = getBatchStatusDisplay(batch.status, !!batch.all_approved)

                  return (
                    <button
                      key={batch.batch_id}
                      className={`sidebar-item ${batch.batch_id === selectedBatchId ? 'active' : ''}`}
                      onClick={() => setSelectedBatchId(batch.batch_id)}
                    >
                      <span className="sidebar-item-name">{batch.batch_id}</span>
                      <span className={`sidebar-badge sidebar-badge-${sidebarStatus.key}`}>
                        {sidebarStatus.label}
                      </span>
                    </button>
                  )
                })}
                {hasNextPage && (
                  <button
                    className="sidebar-item sidebar-load-more"
                    onClick={() => fetchNextPage()}
                    disabled={isFetchingNextPage}
                  >
                    {isFetchingNextPage ? 'Loading...' : `Load more (${batches.length} of ${totalBatches})`}
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </aside>

      <main className="dashboard-main">
        {!selectedBatchId ? (
          <div className="upload-panel directions-panel">
            <h2 className="panel-title">How To Use This Dashboard</h2>
            <p className="panel-description">
              Use one CLI command to create a batch folder and upload notes in your existing deployed bucket. Metadata is created automatically when you click Start De-identification.
            </p>

            <section className="directions-card directions-card-wide directions-command">
              <h3 className="directions-card-title">Upload Notes and Create a New Folder</h3>
              <pre className="cli-command">{createAndUploadCommand}</pre>
              <div className="cli-card-note">
                Replace <code>/PATH/TO/YOUR-NOTES</code> with your local notes folder path.
              </div>
              <div className="cli-card-note">
                If your stack name is not <code>PiiDeidentificationStack</code>, add <code>--stack-name &lt;your-stack-name&gt;</code>.
              </div>

              <p className="directions-text">
                The script prints the batch ID. After running the command, refresh, select your batch, and click Start De-identification.
              </p>
            </section>

            <section className="directions-card">
              <h3 className="directions-card-title">Status Meanings</h3>
              <div className="directions-status-list">
                <div className="directions-status-item">
                  <span className="detail-status-badge detail-status-created">Created</span>
                  <p className="directions-status-description">Batch exists but no input files have been uploaded.</p>
                </div>
                <div className="directions-status-item">
                  <span className="detail-status-badge detail-status-ready-to-process">Ready to Process</span>
                  <p className="directions-status-description">Input files are present and the batch can be started.</p>
                </div>
                <div className="directions-status-item">
                  <span className="detail-status-badge detail-status-processing">Processing</span>
                  <p className="directions-status-description">The worker Lambda is actively processing notes.</p>
                </div>
                <div className="directions-status-item">
                  <span className="detail-status-badge detail-status-partially-completed">Partially Completed</span>
                  <p className="directions-status-description">Some notes processed successfully, but others failed. Click "Retry Failed Notes" to reprocess.</p>
                </div>
                <div className="directions-status-item">
                  <span className="detail-status-badge detail-status-needs-review">Needs Review</span>
                  <p className="directions-status-description">Processing finished, but not all notes are approved.</p>
                </div>
                <div className="directions-status-item">
                  <span className="detail-status-badge detail-status-approved">Approved</span>
                  <p className="directions-status-description">All notes are processed and approved.</p>
                </div>
              </div>
            </section>
          </div>
        ) : (
          <div className={`batch-detail-panel ${isCreatedBatch ? 'batch-detail-panel-created' : ''}`}>
            {batchDetail ? (
              <>
                <div className="batch-header-row">
                  <div className="batch-title-stack">
                    <h2 className="panel-title">{selectedBatchId}</h2>
                    {selectedBatchStatus && (
                      <span className={`detail-status-badge detail-status-${selectedBatchStatus.key}`}>
                        {selectedBatchStatus.label}
                      </span>
                    )}
                  </div>
                  {batchDetail.status === 'completed' && !batchDetail.all_approved && (
                    <button
                      className="btn btn-primary batch-header-approve-btn"
                      onClick={() => handleApproveAll(selectedBatchId)}
                      disabled={approvingAll}
                    >
                      {approvingAll ? 'Approving All...' : 'Approve All'}
                    </button>
                  )}
                </div>

                <div className="batch-metrics-grid">
                  <div className="detail-card metric-card-input">
                    <div className="detail-card-value">{batchDetail.input_count}</div>
                    <div className="detail-card-label">Input Files</div>
                  </div>

                  <div className="metric-processed-stack">
                    <div className="detail-card metric-card-processed">
                      <div className="detail-card-value">{batchDetail.output_count}</div>
                      <div className="detail-card-label">Processed</div>
                    </div>

                    <div className="detail-card metric-card-pii">
                      <div className="detail-card-value">{piiStats?.total_entities ?? 0}</div>
                      <div className="detail-card-label">PII Detected</div>
                    </div>

                    <div className="metric-processed-footer">
                      <div className="batch-buttons-stack">
                        {canStartSelectedBatch && (
                          <button
                            className="btn btn-start action-btn action-btn-start"
                            onClick={() => handleStartBatch(selectedBatchId)}
                            disabled={isStartingSelectedBatch}
                          >
                            {isStartingSelectedBatch ? 'Starting...' : 'Start De-identification'}
                          </button>
                        )}
                        {selectedBatchStatus?.key === 'created' && (
                          <span className="processing-label">
                            Upload notes with the CLI command below to enable processing.
                          </span>
                        )}
                        {batchDetail.status === 'processing' && (
                          <span className="processing-label">Processing... auto-refreshing</span>
                        )}
                        {startError && (
                          <span className="processing-label processing-label-error">
                            Error: {startError}
                          </span>
                        )}
                        {batchDetail.status === 'completed' && (
                          <button
                            className="btn btn-primary action-btn"
                            onClick={() => navigate(`/review/${selectedBatchId}`)}
                          >
                            <span className="action-btn-label">
                              <span className="action-btn-topline">Review</span>
                              <span className="action-btn-subline">Notes</span>
                            </span>
                          </button>
                        )}
                        {batchDetail.status === 'partially-completed' && (
                          <>
                            <div className="failed-notes-message">
                              Some notes failed to process
                            </div>
                            <button
                              className="btn btn-warning action-btn"
                              onClick={() => handleRetryFailedNotes(selectedBatchId)}
                              disabled={retrying}
                            >
                              {retrying ? 'Retrying...' : 'Retry Failed Notes'}
                            </button>
                          </>
                        )}
                      </div>

                      <div className="batch-timeline">
                        {batchDetail.created_at && (
                          <div className="timeline-item">
                            <span className="timeline-label">Created:</span>
                            <span className="timeline-value">{formatTimestamp(batchDetail.created_at)}</span>
                          </div>
                        )}
                        {batchDetail.started_at && (
                          <div className="timeline-item">
                            <span className="timeline-label">Started:</span>
                            <span className="timeline-value">{formatTimestamp(batchDetail.started_at)}</span>
                          </div>
                        )}
                        {batchDetail.failed_at && (
                          <div className="timeline-item timeline-item-warning">
                            <span className="timeline-label">Failed:</span>
                            <span className="timeline-value">{formatTimestamp(batchDetail.failed_at)}</span>
                          </div>
                        )}
                        {batchDetail.last_redrive_at && (
                          <div className="timeline-item">
                            <span className="timeline-label">Retried:</span>
                            <span className="timeline-value">{formatTimestamp(batchDetail.last_redrive_at)}</span>
                          </div>
                        )}
                        {batchDetail.completed_at && (
                          <div className="timeline-item timeline-item-success">
                            <span className="timeline-label">Completed:</span>
                            <span className="timeline-value">{formatTimestamp(batchDetail.completed_at)}</span>
                          </div>
                        )}
                        {batchDetail.approved_at && (
                          <div className="timeline-item timeline-item-success">
                            <span className="timeline-label">Approved:</span>
                            <span className="timeline-value">{formatTimestamp(batchDetail.approved_at)}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="pii-dropdown-panel">
                    <div className="pii-dropdown-title">Detected PII Types</div>
                    {hasBreakdownData ? (
                      <div className="pii-type-list">
                        {piiTypeEntries.map(([entityType, count]) => (
                          <div key={entityType} className="pii-type-row">
                            <span className="pii-type-name">{formatEntityType(entityType)}</span>
                            <span className="pii-type-count">{count}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="pii-type-empty">
                        {piiStats && piiStats.entity_file_count > 0
                          ? 'No PII detected in processed notes.'
                          : 'Waiting for processed notes.'}
                      </div>
                    )}
                  </div>
                </div>

                {isCreatedBatch && (
                  <div className="cli-card batch-cli-card">
                    <div className="cli-card-title">Upload notes for this batch</div>
                    <pre className="cli-command">{uploadToExistingBatchCommandFor(selectedBatchId)}</pre>
                    <div className="cli-card-note">
                      Replace <code>/PATH/TO/YOUR-NOTES</code> with your local notes folder path.
                    </div>
                    <div className="cli-card-note">
                      Re-run with <code>--stack-name &lt;your-stack-name&gt;</code> if needed.
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="loading-state">Loading batch details...</div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
