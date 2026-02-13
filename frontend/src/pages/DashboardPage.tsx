import { useState, useEffect, useRef } from 'react'
import { useQuery, useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import JSZip from 'jszip'
import {
  listBatches,
  createBatch,
  getBatch,
  startBatch,
  getUploadUrl,
  uploadFileToS3,
  listNotes,
  approveAllNotes,
  getDownloadUrl,
  getDetectionDownloadUrl,
  type Batch,
  type Note,
} from '../api/client'
import './DashboardPage.css'

const PAGE_SIZE = 50

export default function DashboardPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [processing, setProcessing] = useState(false)
  const [status, setStatus] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(() => searchParams.get('batch'))

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
    refetchInterval: 10_000,
  })

  const batches = batchPages?.pages.flatMap(p => p.items) ?? []
  const totalBatches = batchPages?.pages[0]?.total ?? 0

  const { data: batchDetail } = useQuery({
    queryKey: ['batch', selectedBatchId],
    queryFn: () => getBatch(selectedBatchId!),
    enabled: !!selectedBatchId,
    refetchInterval: 5_000,
  })

  const addFiles = (files: FileList | File[]) => {
    const incomingFiles = Array.from(files)
    if (incomingFiles.length === 0) return

    setSelectedFiles(prev => {
      const newFiles = incomingFiles.filter(f => !prev.some(s => s.name === f.name))
      return newFiles.length > 0 ? [...prev, ...newFiles] : prev
    })
  }

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : []
    addFiles(files)
    e.target.value = ''
  }

  const removeFile = (name: string) => setSelectedFiles(prev => prev.filter(f => f.name !== name))

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files)
  }

  const handleStart = async () => {
    if (selectedFiles.length === 0) return
    setProcessing(true)
    try {
      setStatus('Creating batch...')
      const batch = await createBatch()
      for (let i = 0; i < selectedFiles.length; i++) {
        setStatus(`Uploading ${i + 1}/${selectedFiles.length}: ${selectedFiles[i].name}`)
        const { upload_url } = await getUploadUrl(batch.batch_id, selectedFiles[i].name)
        await uploadFileToS3(upload_url, selectedFiles[i])
      }
      setStatus('Starting de-identification...')
      await startBatch(batch.batch_id)
      setSelectedFiles([])
      setStatus('')
      queryClient.invalidateQueries({ queryKey: ['batches'] })
      setSelectedBatchId(batch.batch_id)
    } catch (err) {
      setStatus(`Error: ${err instanceof Error ? err.message : 'Failed'}`)
    } finally {
      setProcessing(false)
    }
  }

  const [downloadingRedacted, setDownloadingRedacted] = useState(false)
  const [downloadingDetectedPii, setDownloadingDetectedPii] = useState(false)
  const [approvingAll, setApprovingAll] = useState(false)

  const updateBatchApprovalBadge = (batchId: string, allApproved: boolean) => {
    queryClient.setQueryData(['batches'], (current: any) => {
      if (!current || !Array.isArray(current.pages)) return current
      return {
        ...current,
        pages: current.pages.map((page: any) => ({
          ...page,
          items: Array.isArray(page.items)
            ? page.items.map((batch: any) =>
                batch?.batch_id === batchId ? { ...batch, all_approved: allApproved } : batch,
              )
            : page.items,
        })),
      }
    })
  }

  const loadAllNotes = async (batchId: string) => {
    const limit = 200
    let offset = 0
    let total = Number.POSITIVE_INFINITY
    const notes: Note[] = []

    while (offset < total) {
      const page = await listNotes(batchId, limit, offset)
      notes.push(...page.items)
      total = page.total

      if (page.items.length === 0 || page.items.length < limit) {
        break
      }
      offset += page.items.length
    }

    return notes
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

  const handleDownloadRedacted = async (batchId: string) => {
    setDownloadingRedacted(true)
    try {
      const notes = await loadAllNotes(batchId)
      const downloadable = notes.filter(note => note.has_output)
      const zip = new JSZip()
      for (const note of downloadable) {
        const { download_url } = await getDownloadUrl(batchId, note.note_id)
        const resp = await fetch(download_url)
        if (!resp.ok) {
          throw new Error(`Failed to download redacted note '${note.note_id}' (${resp.status})`)
        }
        const text = await resp.text()
        zip.file(`${note.note_id}_redacted.txt`, text)
      }
      const blob = await zip.generateAsync({ type: 'blob' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${batchId}_redacted_notes.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(a.href)
    } catch (err) {
      alert(`Download error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setDownloadingRedacted(false)
    }
  }

  const handleDownloadDetectedPii = async (batchId: string) => {
    setDownloadingDetectedPii(true)
    try {
      const notes = await loadAllNotes(batchId)
      const downloadable = notes.filter(note => note.has_output)
      const zip = new JSZip()
      for (const note of downloadable) {
        const { download_url } = await getDetectionDownloadUrl(batchId, note.note_id)
        const resp = await fetch(download_url)
        if (!resp.ok) {
          throw new Error(`Failed to download extracted PII for note '${note.note_id}' (${resp.status})`)
        }
        const text = await resp.text()
        zip.file(`${note.note_id}_entities.json`, text)
      }
      const blob = await zip.generateAsync({ type: 'blob' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${batchId}_detected_pii.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(a.href)
    } catch (err) {
      alert(`Download error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setDownloadingDetectedPii(false)
    }
  }

  const statusLabel = (s: string) => {
    const labels: Record<string, string> = { created: 'Created', processing: 'Processing', completed: 'Completed', unknown: 'Unknown' }
    return labels[s] || s
  }

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

  return (
    <div className="dashboard-layout">
      <aside className="dashboard-sidebar">
        <div className="sidebar-section">
          <button
            className={`sidebar-item sidebar-item-new-batch ${!selectedBatchId ? 'active' : ''}`}
            onClick={() => setSelectedBatchId(null)}
          >
            <span className="sidebar-item-icon">+</span>
            <span>New Batch</span>
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
                  const isApprovedBatch = batch.status === 'completed' && !!batch.all_approved
                  const sidebarStatusKey = isApprovedBatch
                    ? 'approved'
                    : batch.status === 'completed'
                      ? 'ready'
                      : batch.status
                  const sidebarStatusText = isApprovedBatch
                    ? 'Approved'
                    : batch.status === 'completed'
                      ? 'Ready'
                      : statusLabel(batch.status)

                  return (
                    <button
                      key={batch.batch_id}
                      className={`sidebar-item ${batch.batch_id === selectedBatchId ? 'active' : ''}`}
                      onClick={() => setSelectedBatchId(batch.batch_id)}
                    >
                      <span className="sidebar-item-name">{batch.batch_id}</span>
                      <span className={`sidebar-badge sidebar-badge-${sidebarStatusKey}`}>
                        {sidebarStatusText}
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
          <div className="upload-panel">
            <h2 className="panel-title">Upload & Process</h2>
            <div
              className={`drop-zone ${dragOver ? 'drag-over' : ''} ${processing ? 'uploading' : ''}`}
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => !processing && fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".txt,.text"
                onChange={handleFileInputChange}
                style={{ display: 'none' }}
              />
              <div className="drop-icon">+</div>
              <p className="drop-text">Drag & drop .txt files here, or click to select</p>
            </div>

            <button
              className="btn btn-start"
              onClick={handleStart}
              disabled={processing || selectedFiles.length === 0}
            >
              {processing ? status || 'Processing...' : `Start De-identification (${selectedFiles.length} files)`}
            </button>

            {selectedFiles.length > 0 && (
              <div className="file-list">
                {selectedFiles.map(f => (
                  <span key={f.name} className="file-tag">
                    {f.name}
                    {!processing && <button className="remove-file" onClick={() => removeFile(f.name)}>&times;</button>}
                  </span>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="batch-detail-panel">
            {batchDetail ? (
              <>
                <div className="batch-header-row">
                  <h2 className="panel-title">{selectedBatchId}</h2>
                  {batchDetail.status === 'completed' && (
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

                  <div className="detail-card metric-card-pii">
                    <div className="detail-card-value">{piiStats?.total_entities ?? 0}</div>
                    <div className="detail-card-label">PII Detected</div>
                  </div>

                  <div className="metric-processed-stack">
                    <div className="detail-card metric-card-processed">
                      <div className="detail-card-value">{batchDetail.output_count}</div>
                      <div className="detail-card-label">Processed</div>
                    </div>

                    <div className="metric-processed-footer">
                      <div className="batch-buttons-stack">
                        {batchDetail.status === 'completed' && (
                          <>
                            <div className="batch-buttons-row batch-buttons-row-single">
                              <button className="btn btn-primary action-btn" onClick={() => navigate(`/review/${selectedBatchId}`)}>
                                <span className="action-btn-label">
                                  <span className="action-btn-topline">Review</span>
                                  <span className="action-btn-subline">Notes</span>
                                </span>
                              </button>
                            </div>
                            <div className="batch-buttons-row">
                              <button
                                className="btn btn-outline action-btn"
                                onClick={() => handleDownloadRedacted(selectedBatchId)}
                                disabled={downloadingRedacted || downloadingDetectedPii}
                              >
                                {downloadingRedacted ? (
                                  'Zipping...'
                                ) : (
                                  <span className="action-btn-label">
                                    <span className="action-btn-topline">
                                      <span className="action-btn-icon" aria-hidden="true">&darr;</span>
                                      <span>Download</span>
                                    </span>
                                    <span className="action-btn-subline">Redacted Notes</span>
                                  </span>
                                )}
                              </button>
                              <button
                                className="btn btn-outline action-btn"
                                onClick={() => handleDownloadDetectedPii(selectedBatchId)}
                                disabled={downloadingRedacted || downloadingDetectedPii}
                              >
                                {downloadingDetectedPii ? (
                                  'Zipping...'
                                ) : (
                                  <span className="action-btn-label">
                                    <span className="action-btn-topline">
                                      <span className="action-btn-icon" aria-hidden="true">&darr;</span>
                                      <span>Download</span>
                                    </span>
                                    <span className="action-btn-subline">Extracted PII</span>
                                  </span>
                                )}
                              </button>
                            </div>
                          </>
                        )}
                        {batchDetail.status === 'processing' && (
                          <span className="processing-label">Processing... auto-refreshing</span>
                        )}
                      </div>

                      {batchDetail.created_at && (
                        <div className="detail-meta">
                          Created: {new Date(batchDetail.created_at).toLocaleString()}
                        </div>
                      )}
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
