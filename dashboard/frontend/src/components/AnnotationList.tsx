import { useState, useMemo } from 'react'
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
  entityType: string | null
  manifestType: string | null
  manifestContext: string | null
}

type MistakeTypeFilter = 'all' | 'fp' | 'fn'

export default function AnnotationList({ mistakes }: AnnotationListProps) {
  const [selectedEntityType, setSelectedEntityType] = useState<string>('all')
  const [selectedMistakeType, setSelectedMistakeType] = useState<MistakeTypeFilter>('all')

  const allAnnotations: FlatAnnotation[] = useMemo(() => {
    const annotations: FlatAnnotation[] = []
    
    for (const doc of mistakes) {
      for (const fp of doc.false_positives) {
        annotations.push({
          docId: doc.doc_id,
          type: 'fp',
          start: fp.start,
          end: fp.end,
          chars: fp.chars,
          entityType: fp.type || null,
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
          entityType: fn.type || fn.manifest_type || null,
          manifestType: fn.manifest_type,
          manifestContext: fn.manifest_context,
        })
      }
    }
    return annotations
  }, [mistakes])

  const entityTypes = useMemo(() => {
    const types = new Set<string>()
    for (const ann of allAnnotations) {
      if (ann.entityType) {
        types.add(ann.entityType)
      }
    }
    return Array.from(types).sort()
  }, [allAnnotations])

  const annotations = useMemo(() => {
    return allAnnotations.filter(ann => {
      const matchesEntityType = selectedEntityType === 'all' || ann.entityType === selectedEntityType
      const matchesMistakeType = selectedMistakeType === 'all' || ann.type === selectedMistakeType
      return matchesEntityType && matchesMistakeType
    })
  }, [allAnnotations, selectedEntityType, selectedMistakeType])

  const sortedAnnotations = [...annotations].sort((a, b) => {
    const docCmp = a.docId.localeCompare(b.docId)
    if (docCmp !== 0) return docCmp
    return a.start - b.start
  })

  // Count from all annotations (before mistake type filter) for display
  const entityFilteredAnnotations = useMemo(() => {
    if (selectedEntityType === 'all') return allAnnotations
    return allAnnotations.filter(ann => ann.entityType === selectedEntityType)
  }, [allAnnotations, selectedEntityType])
  
  const fpCount = entityFilteredAnnotations.filter(a => a.type === 'fp').length
  const fnCount = entityFilteredAnnotations.filter(a => a.type === 'fn').length

  const handleMistakeTypeClick = (type: MistakeTypeFilter) => {
    setSelectedMistakeType(prev => prev === type ? 'all' : type)
  }

  return (
    <div className="annotation-list">
      <div className="list-header">
        <h2 className="section-title">All Mistakes</h2>
        <div className="header-controls">
          <div className="entity-type-filter">
            <label htmlFor="entity-type-select" className="filter-label">Filter by type:</label>
            <select
              id="entity-type-select"
              value={selectedEntityType}
              onChange={(e) => setSelectedEntityType(e.target.value)}
              className="entity-type-select"
            >
              <option value="all">All Types</option>
              {entityTypes.map(type => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </div>
          <div className="counts-summary">
            <button 
              className={`count-btn fp ${selectedMistakeType === 'fp' ? 'active' : ''}`}
              onClick={() => handleMistakeTypeClick('fp')}
              title="Click to filter by False Positives"
            >
              {fpCount} FP
            </button>
            <button 
              className={`count-btn fn ${selectedMistakeType === 'fn' ? 'active' : ''}`}
              onClick={() => handleMistakeTypeClick('fn')}
              title="Click to filter by False Negatives"
            >
              {fnCount} FN
            </button>
          </div>
        </div>
      </div>
      
      {annotations.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">✓</div>
          <div className="empty-text">No mistakes found!</div>
        </div>
      ) : (
        <div className="annotations-scroll">
          {sortedAnnotations.map((ann, idx) => (
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
                {ann.entityType && (
                  <span className="ann-entity-type">{ann.entityType}</span>
                )}
                <span className="ann-pos">{ann.start}–{ann.end}</span>
              </div>
              <div className="ann-content">
                <span className="ann-chars">"{ann.chars || '...'}"</span>
                {ann.type === 'fn' && ann.manifestType && (
                  <span className="ann-type">Expected: {ann.manifestType}</span>
                )}
                {ann.type === 'fp' && ann.entityType && (
                  <span className="ann-type">Predicted: {ann.entityType}</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
