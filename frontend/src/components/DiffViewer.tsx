import { useMemo, useRef, useEffect, useState, useLayoutEffect } from 'react'
import * as Diff from 'diff'
import './DiffViewer.css'

interface DiffViewerProps {
  original: string
  redacted: string
  editableRedacted?: boolean
  onRedactedChange?: (value: string) => void
}

interface DiffChange {
  value: string
  added?: boolean
  removed?: boolean
}

function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(w => w.length > 0).length
}

export default function DiffViewer({
  original,
  redacted,
  editableRedacted = false,
  onRedactedChange,
}: DiffViewerProps) {
  const originalRef = useRef<HTMLElement | null>(null)
  const redactedRef = useRef<HTMLElement | null>(null)
  const redactedScrollTopRef = useRef(0)
  const [syncScrollEnabled, setSyncScrollEnabled] = useState(true)
  const syncScrollEnabledRef = useRef(syncScrollEnabled)
  const lastScrollPositions = useRef({ original: 0, redacted: 0 })

  useEffect(() => {
    syncScrollEnabledRef.current = syncScrollEnabled
    if (syncScrollEnabled && originalRef.current && redactedRef.current) {
      lastScrollPositions.current = {
        original: originalRef.current.scrollTop,
        redacted: redactedRef.current.scrollTop,
      }
      redactedScrollTopRef.current = redactedRef.current.scrollTop
    }
  }, [syncScrollEnabled])

  useLayoutEffect(() => {
    const panel = redactedRef.current
    if (panel) {
      panel.scrollTop = redactedScrollTopRef.current
      lastScrollPositions.current.redacted = panel.scrollTop
    }

    return () => {
      const currentRedactedTop = redactedRef.current?.scrollTop
      if (typeof currentRedactedTop === 'number') {
        redactedScrollTopRef.current = currentRedactedTop
        lastScrollPositions.current.redacted = currentRedactedTop
      }
    }
  }, [editableRedacted])

  const changes = useMemo((): DiffChange[] => Diff.diffWords(original, redacted), [original, redacted])

  const stats = useMemo(() => {
    let removed = 0, added = 0
    for (const c of changes) {
      const wc = countWords(c.value)
      if (c.removed) removed += wc
      else if (c.added) added += wc
    }
    return { removed, added }
  }, [changes])

  useEffect(() => {
    const oPanel = originalRef.current
    const rPanel = redactedRef.current
    if (!oPanel || !rPanel) return

    let isSyncing = false

    const syncScroll = (
      source: HTMLElement,
      sourceKey: 'original' | 'redacted',
      target: HTMLElement,
      targetKey: 'original' | 'redacted',
    ) => {
      if (!syncScrollEnabledRef.current) {
        lastScrollPositions.current[sourceKey] = source.scrollTop
        if (sourceKey === 'redacted') {
          redactedScrollTopRef.current = source.scrollTop
        }
        return
      }
      if (isSyncing) return
      isSyncing = true

      const delta = source.scrollTop - lastScrollPositions.current[sourceKey]
      lastScrollPositions.current[sourceKey] = source.scrollTop
      if (sourceKey === 'redacted') {
        redactedScrollTopRef.current = source.scrollTop
      }

      const newTop = lastScrollPositions.current[targetKey] + delta
      const maxScroll = target.scrollHeight - target.clientHeight
      target.scrollTop = Math.max(0, Math.min(maxScroll, newTop))
      lastScrollPositions.current[targetKey] = target.scrollTop
      if (targetKey === 'redacted') {
        redactedScrollTopRef.current = target.scrollTop
      }

      requestAnimationFrame(() => { isSyncing = false })
    }

    const handleOriginalScroll = () => syncScroll(oPanel, 'original', rPanel, 'redacted')
    const handleRedactedScroll = () => syncScroll(rPanel, 'redacted', oPanel, 'original')

    oPanel.addEventListener('scroll', handleOriginalScroll)
    rPanel.addEventListener('scroll', handleRedactedScroll)

    return () => {
      oPanel.removeEventListener('scroll', handleOriginalScroll)
      rPanel.removeEventListener('scroll', handleRedactedScroll)
    }
  }, [editableRedacted])

  const renderOriginal = (diffs: DiffChange[]) =>
    diffs.map((change, i) => {
      if (change.added) return null
      if (change.removed) return <span key={i} className="diff-removed">{change.value}</span>
      return <span key={i}>{change.value}</span>
    })

  const renderRedacted = (diffs: DiffChange[]) =>
    diffs.map((change, i) => {
      if (change.removed) return null
      if (change.added) return <span key={i} className="diff-added">{change.value}</span>
      return <span key={i}>{change.value}</span>
    })

  return (
    <div className="diff-viewer">
      <div className="diff-toolbar">
        <button
          className={`sync-scroll-btn ${syncScrollEnabled ? 'active' : ''}`}
          onClick={() => setSyncScrollEnabled(v => !v)}
        >
          {syncScrollEnabled ? 'Sync On' : 'Sync Off'}
        </button>
        <div className="diff-legend">
          <span className="legend-item">
            <span className="legend-color legend-removed"></span>
            PHI (removed)
          </span>
          <span className="legend-item">
            <span className="legend-color legend-added"></span>
            Redacted (replaced)
          </span>
        </div>
      </div>

      <div className="diff-panels">
        <div className="diff-panel">
          <div className="diff-panel-header">
            <span className="diff-panel-label">Original</span>
            <span className="diff-panel-stats">{countWords(original)} words</span>
          </div>
          <div
            className="diff-panel-content"
            ref={(element) => {
              originalRef.current = element
            }}
          >
            <pre className="diff-text">{renderOriginal(changes)}</pre>
          </div>
        </div>

        <div className="diff-panel">
          <div className="diff-panel-header">
            <span className="diff-panel-label">Redacted</span>
            <span className="diff-panel-stats diff-stats-info">
              {stats.removed} removed &middot; {stats.added} replaced
            </span>
          </div>
          {editableRedacted ? (
            <textarea
              className="diff-text diff-text-editable"
              value={redacted}
              onChange={(event) => onRedactedChange?.(event.target.value)}
              readOnly={!onRedactedChange}
              spellCheck={false}
              ref={(element) => {
                redactedRef.current = element
              }}
            />
          ) : (
            <div
              className="diff-panel-content"
              ref={(element) => {
                redactedRef.current = element
              }}
            >
              <pre className="diff-text">{renderRedacted(changes)}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
