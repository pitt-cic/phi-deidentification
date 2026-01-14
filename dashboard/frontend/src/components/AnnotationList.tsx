import { Link } from 'react-router-dom'
import type { DocumentMistakes } from '../api/types'
import './AnnotationList.css'

interface AnnotationListProps {
  mistakes: DocumentMistakes[]
}

interface FlatAnnotation {
  docId: string
  type: 'fp' | 'fn'
  start: number
  end: number
  chars: string | null
  manifestType: string | null
  manifestContext: string | null
}

export default function AnnotationList({ mistakes }: AnnotationListProps) {
  // Flatten all mistakes into a single list
  const annotations: FlatAnnotation[] = []
  
  for (const doc of mistakes) {
    for (const fp of doc.false_positives) {
      annotations.push({
        docId: doc.doc_id,
        type: 'fp',
        start: fp.start,
        end: fp.end,
        chars: fp.chars,
        manifestType: null,
        manifestContext: null,
      })
    }
    for (const fn of doc.false_negatives) {
      annotations.push({
        docId: doc.doc_id,
        type: 'fn',
        start: fn.start,
        end: fn.end,
        chars: fn.chars,
        manifestType: fn.manifest_type,
        manifestContext: fn.manifest_context,
      })
    }
  }

  // Sort by document, then by position
  annotations.sort((a, b) => {
    const docCmp = a.docId.localeCompare(b.docId)
    if (docCmp !== 0) return docCmp
    return a.start - b.start
  })

  const fpCount = annotations.filter(a => a.type === 'fp').length
  const fnCount = annotations.filter(a => a.type === 'fn').length

  return (
    <div className="annotation-list">
      <div className="list-header">
        <h2 className="section-title">All Mistakes</h2>
        <div className="counts-summary">
          <span className="count fp">{fpCount} FP</span>
          <span className="count fn">{fnCount} FN</span>
        </div>
      </div>
      
      {annotations.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">✓</div>
          <div className="empty-text">No mistakes found!</div>
        </div>
      ) : (
        <div className="annotations-scroll">
          {annotations.map((ann, idx) => (
            <Link
              key={`${ann.docId}-${ann.type}-${ann.start}-${idx}`}
              to={`/note/${ann.docId}?highlight=${ann.start}`}
              className={`annotation-item ${ann.type}`}
            >
              <div className="ann-header">
                <span className={`ann-badge ${ann.type}`}>
                  {ann.type === 'fp' ? 'FP' : 'FN'}
                </span>
                <span className="ann-doc">{ann.docId}</span>
                <span className="ann-pos">{ann.start}–{ann.end}</span>
              </div>
              <div className="ann-content">
                <span className="ann-chars">"{ann.chars || '...'}"</span>
                {ann.manifestType && (
                  <span className="ann-type">Expected: {ann.manifestType}</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}



