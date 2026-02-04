import { useMemo, useRef, useEffect, useState } from 'react'
import * as Diff from 'diff'
import './ThreePanelDiff.css'

interface ThreePanelDiffProps {
  original: string
  llmOutput: string
  groundTruth: string
}

interface DiffChange {
  value: string
  added?: boolean
  removed?: boolean
}

interface DiffStats {
  redacted: number
  unchanged: number
}

// Count words in a string (split by whitespace)
function countWords(text: string): number {
  return text.trim().split(/\s+/).filter(w => w.length > 0).length
}

// Compute diff stats
function computeStats(changes: DiffChange[]): DiffStats {
  let redacted = 0
  let unchanged = 0

  for (const change of changes) {
    const wordCount = countWords(change.value)
    if (change.removed) {
      redacted += wordCount
    } else if (!change.added) {
      unchanged += wordCount
    }
  }

  return { redacted, unchanged }
}

export default function ThreePanelDiff({
  original,
  llmOutput,
  groundTruth,
}: ThreePanelDiffProps) {
  const originalPanelRef = useRef<HTMLDivElement>(null)
  const llmPanelRef = useRef<HTMLDivElement>(null)
  const gtPanelRef = useRef<HTMLDivElement>(null)
  const [syncScrollEnabled, setSyncScrollEnabled] = useState(true)
  const syncScrollEnabledRef = useRef(syncScrollEnabled)

  // Track last scroll positions for delta-based sync
  const lastScrollPositions = useRef<{ original: number; llm: number; gt: number }>({
    original: 0,
    llm: 0,
    gt: 0,
  })

  // Keep ref in sync with state
  useEffect(() => {
    syncScrollEnabledRef.current = syncScrollEnabled

    // When sync is re-enabled, capture current positions as the new baseline
    if (syncScrollEnabled) {
      const originalPanel = originalPanelRef.current
      const llmPanel = llmPanelRef.current
      const gtPanel = gtPanelRef.current

      if (originalPanel && llmPanel && gtPanel) {
        lastScrollPositions.current = {
          original: originalPanel.scrollTop,
          llm: llmPanel.scrollTop,
          gt: gtPanel.scrollTop,
        }
      }
    }
  }, [syncScrollEnabled])

  // Compute diffs: Original vs LLM, Original vs GT
  const llmChanges = useMemo((): DiffChange[] => {
    return Diff.diffWords(original, llmOutput)
  }, [original, llmOutput])

  const gtChanges = useMemo((): DiffChange[] => {
    return Diff.diffWords(original, groundTruth)
  }, [original, groundTruth])

  // Stats for each diff
  const llmStats = useMemo(() => computeStats(llmChanges), [llmChanges])
  const gtStats = useMemo(() => computeStats(gtChanges), [gtChanges])

  // Synchronized scrolling across all three panels using delta-based approach
  useEffect(() => {
    const originalPanel = originalPanelRef.current
    const llmPanel = llmPanelRef.current
    const gtPanel = gtPanelRef.current

    if (!originalPanel || !llmPanel || !gtPanel) return

    let isSyncing = false

    const syncScroll = (
      source: HTMLDivElement,
      sourceKey: 'original' | 'llm' | 'gt',
      targets: { panel: HTMLDivElement; key: 'original' | 'llm' | 'gt' }[]
    ) => {
      if (!syncScrollEnabledRef.current) {
        // Update last position even when sync is off
        lastScrollPositions.current[sourceKey] = source.scrollTop
        return
      }
      if (isSyncing) return
      isSyncing = true

      // Calculate delta from last known position
      const delta = source.scrollTop - lastScrollPositions.current[sourceKey]

      // Update source's last position
      lastScrollPositions.current[sourceKey] = source.scrollTop

      // Apply delta to targets
      for (const { panel, key } of targets) {
        const newScrollTop = lastScrollPositions.current[key] + delta
        // Clamp to valid range
        const maxScroll = panel.scrollHeight - panel.clientHeight
        panel.scrollTop = Math.max(0, Math.min(maxScroll, newScrollTop))
        lastScrollPositions.current[key] = panel.scrollTop
      }

      requestAnimationFrame(() => {
        isSyncing = false
      })
    }

    const handleOriginalScroll = () => syncScroll(
      originalPanel,
      'original',
      [{ panel: llmPanel, key: 'llm' }, { panel: gtPanel, key: 'gt' }]
    )
    const handleLLMScroll = () => syncScroll(
      llmPanel,
      'llm',
      [{ panel: originalPanel, key: 'original' }, { panel: gtPanel, key: 'gt' }]
    )
    const handleGTScroll = () => syncScroll(
      gtPanel,
      'gt',
      [{ panel: originalPanel, key: 'original' }, { panel: llmPanel, key: 'llm' }]
    )

    originalPanel.addEventListener('scroll', handleOriginalScroll)
    llmPanel.addEventListener('scroll', handleLLMScroll)
    gtPanel.addEventListener('scroll', handleGTScroll)

    return () => {
      originalPanel.removeEventListener('scroll', handleOriginalScroll)
      llmPanel.removeEventListener('scroll', handleLLMScroll)
      gtPanel.removeEventListener('scroll', handleGTScroll)
    }
  }, [])

  // Render the output panel with diff highlighting
  // Shows what was ADDED (the redaction placeholders) and what's unchanged
  // Removed text from original = redactions (shown as highlighted additions in output)
  const renderDiffPanel = (changes: DiffChange[]) => {
    const elements: React.ReactNode[] = []

    changes.forEach((change, index) => {
      const key = `${index}-${change.value.slice(0, 10)}`

      if (change.added) {
        // This is the redaction placeholder that replaced the original text
        elements.push(
          <span key={key} className="diff-redaction">
            {change.value}
          </span>
        )
      } else if (change.removed) {
        // This was removed from original (we don't show it in the output panel)
        // Skip it - it's been redacted
      } else {
        // Unchanged text
        elements.push(
          <span key={key} className="diff-unchanged">
            {change.value}
          </span>
        )
      }
    })

    return elements
  }

  return (
    <div className="three-panel-diff">
      <div className="three-panel-toolbar">
        <button
          className={`sync-scroll-btn ${syncScrollEnabled ? 'active' : ''}`}
          onClick={() => setSyncScrollEnabled(!syncScrollEnabled)}
          title={syncScrollEnabled ? 'Disable synchronized scrolling' : 'Enable synchronized scrolling'}
        >
          {syncScrollEnabled ? 'Sync On' : 'Sync Off'}
        </button>
        <div className="three-panel-legend">
          <span className="legend-item">
            <span className="legend-color legend-redaction"></span>
            Redacted (replaced)
          </span>
          <span className="legend-item">
            <span className="legend-color legend-unchanged"></span>
            Unchanged
          </span>
        </div>
      </div>

      <div className="three-panel-content">
        <div className="diff-panel">
          <div className="diff-panel-header">
            <span className="diff-panel-label">Original</span>
            <span className="diff-panel-stats">
              {countWords(original)} words
            </span>
          </div>
          <div className="diff-panel-content" ref={originalPanelRef}>
            <pre className="diff-text">{original}</pre>
          </div>
        </div>

        <div className="diff-panel">
          <div className="diff-panel-header">
            <span className="diff-panel-label">LLM Output</span>
            <span className="diff-panel-stats diff-stats-redacted">
              {llmStats.redacted} redacted
            </span>
          </div>
          <div className="diff-panel-content" ref={llmPanelRef}>
            <pre className="diff-text">{renderDiffPanel(llmChanges)}</pre>
          </div>
        </div>

        <div className="diff-panel">
          <div className="diff-panel-header">
            <span className="diff-panel-label">Ground Truth</span>
            <span className="diff-panel-stats diff-stats-redacted">
              {gtStats.redacted} redacted
            </span>
          </div>
          <div className="diff-panel-content" ref={gtPanelRef}>
            <pre className="diff-text">{renderDiffPanel(gtChanges)}</pre>
          </div>
        </div>
      </div>
    </div>
  )
}
