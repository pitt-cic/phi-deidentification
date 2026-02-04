import { useState, useEffect, useRef, useMemo } from 'react'
import type { AnnotationSpan } from '../api/types'
import './NoteViewer.css'

type ViewMode = 'evaluation' | 'redacted'

interface NoteViewerProps {
  noteId: string
  text: string
  redactedText?: string
  spans: AnnotationSpan[]
  highlightPosition?: number
}

interface TooltipInfo {
  span: AnnotationSpan
  x: number
  y: number
}

export default function NoteViewer({ noteId, text, redactedText, spans, highlightPosition }: NoteViewerProps) {
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('evaluation')
  const containerRef = useRef<HTMLDivElement>(null)
  const highlightRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (highlightPosition !== undefined && highlightRef.current && viewMode === 'evaluation') {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [highlightPosition, viewMode])

  const segments = useMemo(() => {
    if (spans.length === 0) {
      return [{ start: 0, end: text.length, text, span: null }]
    }

    const sortedSpans = [...spans].sort((a, b) => a.start - b.start)
    const result: Array<{ start: number; end: number; text: string; span: AnnotationSpan | null }> = []
    let currentPos = 0

    for (const span of sortedSpans) {
      if (span.start > currentPos) {
        result.push({
          start: currentPos,
          end: span.start,
          text: text.slice(currentPos, span.start),
          span: null,
        })
      }

      if (span.start >= currentPos) {
        result.push({
          start: span.start,
          end: span.end,
          text: text.slice(span.start, span.end),
          span,
        })
        currentPos = span.end
      }
    }

    if (currentPos < text.length) {
      result.push({
        start: currentPos,
        end: text.length,
        text: text.slice(currentPos),
        span: null,
      })
    }

    return result
  }, [text, spans])

  const handleMouseEnter = (span: AnnotationSpan, event: React.MouseEvent) => {
    const rect = (event.target as HTMLElement).getBoundingClientRect()
    const containerRect = containerRef.current?.getBoundingClientRect()

    if (containerRect) {
      setTooltip({
        span,
        x: rect.left - containerRect.left + rect.width / 2,
        y: rect.top - containerRect.top - 10,
      })
    }
  }

  const handleMouseLeave = () => {
    setTooltip(null)
  }

  const getClassificationLabel = (classification: string) => {
    switch (classification) {
      case 'tp': return 'True Positive'
      case 'fp': return 'False Positive'
      case 'fn': return 'False Negative'
      default: return classification
    }
  }

  const hasRedacted = !!redactedText

  return (
    <div className="note-viewer" ref={containerRef}>
      <div className="note-header">
        <h2 className="note-title">{noteId}</h2>

        {viewMode === 'evaluation' && (
          <div className="legend">
            <span className="legend-item tp">
              <span className="legend-swatch"></span>
              True Positive
            </span>
            <span className="legend-item fp">
              <span className="legend-swatch"></span>
              False Positive
            </span>
            <span className="legend-item fn">
              <span className="legend-swatch"></span>
              False Negative
            </span>
          </div>
        )}

        {hasRedacted && (
          <div className="view-toggle">
            <button
              className={`toggle-btn ${viewMode === 'evaluation' ? 'active' : ''}`}
              onClick={() => setViewMode('evaluation')}
            >
              Evaluation
            </button>
            <button
              className={`toggle-btn ${viewMode === 'redacted' ? 'active' : ''}`}
              onClick={() => setViewMode('redacted')}
            >
              Redacted
            </button>
          </div>
        )}
      </div>

      <div className="note-content">
        {viewMode === 'redacted' && redactedText ? (
          <pre className="note-text">{redactedText}</pre>
        ) : (
          <pre className="note-text">
            {segments.map((segment, idx) => {
              if (!segment.span) {
                return <span key={idx}>{segment.text}</span>
              }

              const isHighlighted = highlightPosition !== undefined &&
                segment.start <= highlightPosition &&
                highlightPosition < segment.end

              return (
                <span
                  key={idx}
                  ref={isHighlighted ? highlightRef : undefined}
                  className={`highlight ${segment.span.classification} ${isHighlighted ? 'active' : ''}`}
                  onMouseEnter={(e) => handleMouseEnter(segment.span!, e)}
                  onMouseLeave={handleMouseLeave}
                >
                  {segment.text}
                </span>
              )
            })}
          </pre>
        )}
      </div>

      {tooltip && viewMode === 'evaluation' && (
        <div
          className="annotation-tooltip"
          style={{
            left: tooltip.x,
            top: tooltip.y,
          }}
        >
          <div className={`tooltip-badge ${tooltip.span.classification}`}>
            {getClassificationLabel(tooltip.span.classification)}
          </div>
          <div className="tooltip-content">
            <div className="tooltip-row">
              <span className="tooltip-label">Text:</span>
              <span className="tooltip-value monospace">"{tooltip.span.text}"</span>
            </div>
            {tooltip.span.predicted_type && (
              <div className="tooltip-row">
                <span className="tooltip-label">Predicted:</span>
                <span className="tooltip-value">{tooltip.span.predicted_type}</span>
              </div>
            )}
            {tooltip.span.expected_type && (
              <div className="tooltip-row">
                <span className="tooltip-label">Expected:</span>
                <span className="tooltip-value">{tooltip.span.expected_type}</span>
              </div>
            )}
            <div className="tooltip-row">
              <span className="tooltip-label">Position:</span>
              <span className="tooltip-value monospace">{tooltip.span.start}–{tooltip.span.end}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
