import type {
  EvaluationSummary,
  EvaluationDetail,
  DocumentMistakes,
  NoteSummary,
  NoteContent,
  NoteAnnotations,
  SafeHarborComparison,
  SafeHarborMetrics,
} from './types'

const API_BASE = '/api'

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`)
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export async function listEvaluations(): Promise<EvaluationSummary[]> {
  return fetchJson('/evaluations')
}

export async function getEvaluation(evalId: string): Promise<EvaluationDetail> {
  return fetchJson(`/evaluations/${evalId}`)
}

export async function getEvaluationMistakes(evalId: string): Promise<DocumentMistakes[]> {
  return fetchJson(`/evaluations/${evalId}/mistakes`)
}

export async function listNotes(evalId?: string): Promise<NoteSummary[]> {
  const params = evalId ? `?eval_id=${evalId}` : ''
  return fetchJson(`/notes${params}`)
}

export async function getNote(noteId: string): Promise<NoteContent> {
  return fetchJson(`/notes/${noteId}`)
}

export async function getNoteRedacted(noteId: string): Promise<NoteContent> {
  return fetchJson(`/notes/${noteId}/redacted`)
}

export async function getNoteAnnotations(noteId: string): Promise<NoteAnnotations> {
  return fetchJson(`/notes/${noteId}/annotations`)
}

export async function listSafeHarborNotes(): Promise<NoteSummary[]> {
  return fetchJson('/safe-harbor/notes')
}

export async function getSafeHarborComparison(noteId: string): Promise<SafeHarborComparison> {
  return fetchJson(`/safe-harbor/notes/${noteId}/comparison`)
}

export async function getSafeHarborMetrics(): Promise<SafeHarborMetrics> {
  return fetchJson('/safe-harbor/metrics')
}
