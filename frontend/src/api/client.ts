import { fetchAuthSession } from 'aws-amplify/auth'

export interface Batch {
  batch_id: string
  created_at: string
  status: 'created' | 'processing' | 'completed' | 'unknown'
}

export interface BatchDetail extends Batch {
  input_count: number
  output_count: number
}

export interface Note {
  note_id: string
  filename: string
  has_output: boolean
  approved: boolean
}

export interface PIIEntity {
  type: string
  value: string
}

export interface NoteDetail {
  note_id: string
  original_text: string
  redacted_text: string
  pii_entities: PIIEntity[]
  summary: string
  needs_review: boolean
  approved: boolean
}

export interface UploadUrlResponse {
  upload_url: string
  key: string
}

export interface DownloadUrlResponse {
  download_url: string
  key: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface ApprovalResponse {
  note_id: string
  approved: boolean
  timestamp: string
}

const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

async function getAuthHeaders(): Promise<Record<string, string>> {
  try {
    const session = await fetchAuthSession()
    const token = session.tokens?.idToken?.toString()
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: token } : {}),
    }
  } catch {
    return { 'Content-Type': 'application/json' }
  }
}

async function fetchApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = await getAuthHeaders()
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string> || {}) },
  })
  if (!response.ok) {
    const errorBody = await response.text().catch(() => '')
    throw new Error(`API error ${response.status}: ${errorBody || response.statusText}`)
  }
  return response.json()
}

export async function listBatches(limit = 50, offset = 0): Promise<PaginatedResponse<Batch>> {
  const data = await fetchApi<PaginatedResponse<Batch> | Batch[]>(`/batches?limit=${limit}&offset=${offset}`)
  if (Array.isArray(data)) return { items: data, total: data.length, limit: data.length, offset: 0 }
  return data
}

export async function createBatch(batchId?: string): Promise<Batch> {
  return fetchApi('/batches', {
    method: 'POST',
    body: JSON.stringify(batchId ? { batch_id: batchId } : {}),
  })
}

export async function getBatch(batchId: string): Promise<BatchDetail> {
  return fetchApi(`/batches/${batchId}`)
}

export async function startBatch(batchId: string): Promise<{ status: string; batch_id: string }> {
  return fetchApi(`/batches/${batchId}/start`, { method: 'POST' })
}

export async function getUploadUrl(batchId: string, filename: string): Promise<UploadUrlResponse> {
  return fetchApi(`/batches/${batchId}/upload-url`, {
    method: 'POST',
    body: JSON.stringify({ filename }),
  })
}

export async function uploadFileToS3(presignedUrl: string, file: File): Promise<void> {
  const response = await fetch(presignedUrl, {
    method: 'PUT',
    body: file,
    headers: { 'Content-Type': 'text/plain' },
  })
  if (!response.ok) throw new Error(`Upload failed: ${response.status}`)
}

export async function listNotes(batchId: string, limit = 50, offset = 0): Promise<PaginatedResponse<Note>> {
  const data = await fetchApi<PaginatedResponse<Note> | Note[]>(`/batches/${batchId}/notes?limit=${limit}&offset=${offset}`)
  if (Array.isArray(data)) return { items: data, total: data.length, limit: data.length, offset: 0 }
  return data
}

export async function getNote(batchId: string, noteId: string): Promise<NoteDetail> {
  return fetchApi(`/batches/${batchId}/notes/${noteId}`)
}

export async function approveNote(batchId: string, noteId: string, approved: boolean): Promise<ApprovalResponse> {
  return fetchApi(`/batches/${batchId}/notes/${noteId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ approved }),
  })
}

export async function getDownloadUrl(batchId: string, noteId: string): Promise<DownloadUrlResponse> {
  return fetchApi(`/batches/${batchId}/notes/${noteId}/download-url`)
}
