export interface EvaluationSummary {
  eval_id: string
  timestamp: string
  num_files: number
  precision: number
  recall: number
  f1: number
}

export interface MetricsSummary {
  precision: number
  recall: number
  f1: number
  true_positives: number
  false_positives: number
  false_negatives: number
}

export interface TypeMetrics {
  type_name: string
  precision: number
  recall: number
  f1: number
  true_positives: number
  false_positives: number
  false_negatives: number
}

export interface FileMetrics {
  file_id: string
  precision: number
  recall: number
  f1: number
  true_positives: number
  false_positives: number
  false_negatives: number
}

export interface EvaluationDetail {
  eval_id: string
  settings: Record<string, unknown>
  aggregate: MetricsSummary
  by_type: TypeMetrics[]
  per_file: FileMetrics[]
}

export interface MistakeEntry {
  start: number
  end: number
  chars: string | null
  manifest_context: string | null
  manifest_type: string | null
}

export interface DocumentMistakes {
  doc_id: string
  false_positive_count: number
  false_negative_count: number
  false_positives: MistakeEntry[]
  false_negatives: MistakeEntry[]
}

export interface NoteSummary {
  note_id: string
  note_type: string | null
  has_mistakes: boolean
}

export interface NoteContent {
  note_id: string
  text: string
}

export interface AnnotationSpan {
  start: number
  end: number
  text: string
  classification: 'tp' | 'fp' | 'fn'
  predicted_type: string | null
  expected_type: string | null
}

export interface NoteAnnotations {
  note_id: string
  spans: AnnotationSpan[]
}



