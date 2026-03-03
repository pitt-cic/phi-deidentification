import { fetchAuthSession } from 'aws-amplify/auth'
import type { InfiniteData } from '@tanstack/react-query'

export interface Batch {
  batch_id: string
  created_at: string
  status: 'created' | 'ready' | 'processing' | 'completed' | 'partially-completed' | 'unknown'
  all_approved?: boolean
}

export interface BatchDetail extends Batch {
  input_count: number
  output_count: number
  pii_stats?: BatchPIIStats
  started_at?: string
  completed_at?: string
  failed_at?: string
  last_redrive_at?: string
  approved_at?: string
}

export interface BatchPIIStats {
  entity_file_count: number
  total_entities: number
  by_type: Record<string, number>
}

export interface Note {
  note_id: string
  has_output: boolean
  approved: boolean
}

export interface NoteDetail {
  note_id: string
  original_text: string
  redacted_text: string
  output_redacted_text?: string
  needs_review: boolean
  approved: boolean
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
  redacted_text: string
  timestamp: string
}

export interface ApproveNotePayload {
  approved: boolean
  redacted_text?: string
}

export interface ApproveAllResponse {
  batch_id: string
  required_note_count: number
  approved_note_count: number
  all_approved: boolean
}

export type BatchesQueryData = InfiniteData<PaginatedResponse<Batch>, number>

export const PAGE_SIZE = 50

const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

function getSanitizedErrorMessage(status: number): string {
  if (status === 400) return 'Invalid request. Please review your input and try again.'
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return 'You do not have permission to perform this action.'
  if (status === 404) return 'The requested resource could not be found.'
  if (status === 429) return 'Too many requests. Please wait a moment and try again.'
  if (status >= 500) return 'A server error occurred. Please try again shortly.'
  return 'Request failed. Please try again.'
}

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
  const start = performance.now()
  const headers = await getAuthHeaders()
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string> || {}) },
  })
  if (!response.ok) {
    const status = response.status
    const requestId = response.headers.get('x-amzn-requestid')
      || response.headers.get('x-amz-request-id')
      || response.headers.get('x-request-id')

    if (import.meta.env.DEV) {
      const errorBody = await response.text().catch(() => '')
      throw new Error(`API error ${status}: ${errorBody || response.statusText}`)
    }

    const safeMessage = getSanitizedErrorMessage(status)
    throw new Error(requestId ? `${safeMessage} (ref: ${requestId})` : safeMessage)
  }
  const data = await response.json()
  if (import.meta.env.DEV) {
    const duration = performance.now() - start
    console.log(`[API] ${options.method || 'GET'} ${path} - ${duration.toFixed(0)}ms`)
  }
  return data
}

export async function listBatches(limit = PAGE_SIZE, offset = 0): Promise<PaginatedResponse<Batch>> {
  const data = await fetchApi<PaginatedResponse<Batch> | Batch[]>(`/batches?limit=${limit}&offset=${offset}`)
  if (Array.isArray(data)) return { items: data, total: data.length, limit: data.length, offset: 0 }
  return data
}

export async function getBatch(batchId: string): Promise<BatchDetail> {
  return fetchApi(`/batches/${batchId}`)
}

export async function startBatch(batchId: string): Promise<{ status: string; batch_id: string }> {
  return fetchApi(`/batches/${batchId}/start`, { method: 'POST' })
}

export async function listNotes(batchId: string, limit = PAGE_SIZE, offset = 0): Promise<PaginatedResponse<Note>> {
  const data = await fetchApi<PaginatedResponse<Note> | Note[]>(`/batches/${batchId}/notes?limit=${limit}&offset=${offset}`)
  if (Array.isArray(data)) return { items: data, total: data.length, limit: data.length, offset: 0 }
  return data
}

export async function getNote(batchId: string, noteId: string): Promise<NoteDetail> {
  return fetchApi(`/batches/${batchId}/notes/${noteId}`)
}

export async function approveNote(batchId: string, noteId: string, payload: ApproveNotePayload): Promise<ApprovalResponse> {
  return fetchApi(`/batches/${batchId}/notes/${noteId}/approve`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function approveAllNotes(batchId: string): Promise<ApproveAllResponse> {
  return fetchApi(`/batches/${batchId}/approve-all`, {
    method: 'POST',
  })
}

export async function redriveBatch(batchId: string): Promise<{ batch_id: string; redriven_count: number; status: string }> {
  return fetchApi(`/batches/${batchId}/redrive`, { method: 'POST' })
}
