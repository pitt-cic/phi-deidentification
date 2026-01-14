import { useState, useEffect, useRef, useMemo } from 'react'
import type { AnnotationSpan } from '../api/types'
import './NoteViewer.css'

interface NoteViewerProps {
  noteId: string
  text: string
  spans: AnnotationSpan[]
  highlightPosition?: number
}

interface TooltipInfo {
  span: AnnotationSpan
  x: number
  y: number
}

export default function NoteViewer({ noteId, text, spans, highlightPosition }: NoteViewerProps) {
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const highlightRef = useRef<HTMLSpanElement>(null)

  // Scroll to highlight position when it changes
  useEffect(() => {
    if (highlightPosition !== undefined && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [highlightPosition])

  // Build rendered segments with non-overlapping spans
  const segments = useMemo(() => {
    if (spans.length === 0) {
      return [{ start: 0, end: text.length, text, span: null }]
    }

    // Sort spans by start position
    const sortedSpans = [...spans].sort((a, b) => a.start - b.start)
    
    const result: Array<{ start: number; end: number; text: string; span: AnnotationSpan | null }> = []
    let currentPos = 0

    for (const span of sortedSpans) {
      // Add text before this span (if any)
      if (span.start > currentPos) {
        result.push({
          start: currentPos,
          end: span.start,
          text: text.slice(currentPos, span.start),
          span: null,
        })
      }

      // Add the span itself
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

    // Add remaining text after all spans
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

  return (
    <div className="note-viewer" ref={containerRef}>
      <div className="note-header">
        <h2 className="note-title">{noteId}</h2>
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
      </div>

      <div className="note-content">
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
      </div>

      {tooltip && (
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



