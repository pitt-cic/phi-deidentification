import { useState, useCallback, useRef } from 'react'
import { useQuery, useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import JSZip from 'jszip'
import {
  listBatches,
  createBatch,
  getBatch,
  startBatch,
  getUploadUrl,
  uploadFileToS3,
  listNotes,
  getDownloadUrl,
  type Batch,
} from '../api/client'
import './DashboardPage.css'

const PAGE_SIZE = 50

export default function DashboardPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [processing, setProcessing] = useState(false)
  const [status, setStatus] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null)

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
    const newFiles = Array.from(files).filter(f => !selectedFiles.some(s => s.name === f.name))
    if (newFiles.length > 0) setSelectedFiles(prev => [...prev, ...newFiles])
  }

  const removeFile = (name: string) => setSelectedFiles(prev => prev.filter(f => f.name !== name))

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files)
  }, [selectedFiles])

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

  const [downloading, setDownloading] = useState(false)

  const handleDownload = async (batchId: string) => {
    setDownloading(true)
    try {
      const { items: notes } = await listNotes(batchId, 1000)
      const downloadable = notes.filter(n => n.has_output)
      const zip = new JSZip()
      for (const note of downloadable) {
        const { download_url } = await getDownloadUrl(batchId, note.note_id)
        const resp = await fetch(download_url)
        const text = await resp.text()
        zip.file(`${note.note_id}_redacted.txt`, text)
      }
      const blob = await zip.generateAsync({ type: 'blob' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${batchId}.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(a.href)
    } catch (err) {
      alert(`Download error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setDownloading(false)
    }
  }

  const statusLabel = (s: string) => {
    const labels: Record<string, string> = { created: 'Created', processing: 'Processing', completed: 'Completed', unknown: 'Unknown' }
    return labels[s] || s
  }

  return (
    <div className="dashboard-layout">
      <aside className="dashboard-sidebar">
        <div className="sidebar-section">
          <button
            className={`sidebar-item ${!selectedBatchId ? 'active' : ''}`}
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
                {batches.map((batch: Batch) => (
                  <button
                    key={batch.batch_id}
                    className={`sidebar-item ${batch.batch_id === selectedBatchId ? 'active' : ''}`}
                    onClick={() => setSelectedBatchId(batch.batch_id)}
                  >
                    <span className="sidebar-item-name">{batch.batch_id}</span>
                    <span className={`sidebar-badge sidebar-badge-${batch.status}`}>
                      {statusLabel(batch.status)}
                    </span>
                  </button>
                ))}
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
                onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = '' }}
                style={{ display: 'none' }}
              />
              <div className="drop-icon">+</div>
              <p className="drop-text">Drag & drop .txt files here, or click to select</p>
            </div>

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

            <button
              className="btn btn-start"
              onClick={handleStart}
              disabled={processing || selectedFiles.length === 0}
            >
              {processing ? status || 'Processing...' : `Start De-identification (${selectedFiles.length} files)`}
            </button>
          </div>
        ) : (
          <div className="batch-detail-panel">
            <h2 className="panel-title">{selectedBatchId}</h2>

            {batchDetail ? (
              <>
                <div className="detail-cards">
                  <div className="detail-card">
                    <div className="detail-card-value">{statusLabel(batchDetail.status)}</div>
                    <div className="detail-card-label">Status</div>
                  </div>
                  <div className="detail-card">
                    <div className="detail-card-value">{batchDetail.input_count}</div>
                    <div className="detail-card-label">Input Files</div>
                  </div>
                  <div className="detail-card">
                    <div className="detail-card-value">{batchDetail.output_count}</div>
                    <div className="detail-card-label">Processed</div>
                  </div>
                </div>

                {batchDetail.input_count > 0 && (
                  <div className="detail-progress">
                    <div className="progress-bar">
                      <div
                        className="progress-fill"
                        style={{ width: `${Math.round((batchDetail.output_count / batchDetail.input_count) * 100)}%` }}
                      />
                    </div>
                    <span className="progress-label">
                      {batchDetail.output_count} / {batchDetail.input_count} processed
                    </span>
                  </div>
                )}

                <div className="detail-actions">
                  {batchDetail.status === 'completed' && (
                    <>
                      <button className="btn btn-primary" onClick={() => navigate(`/review/${selectedBatchId}`)}>
                        Review Notes
                      </button>
                      <button className="btn btn-outline" onClick={() => handleDownload(selectedBatchId)} disabled={downloading}>
                        {downloading ? 'Zipping...' : 'Download All (.zip)'}
                      </button>
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
