import { useQuery } from '@tanstack/react-query'
import { getEvaluation, getEvaluationMistakes } from '../api/client'
import MetricsOverview from '../components/MetricsOverview'
import TypeBreakdownTable from '../components/TypeBreakdownTable'
import AnnotationList from '../components/AnnotationList'
import SafeHarborNotes from '../components/SafeHarborNotes'
import { useState, useMemo } from 'react'
import type { FileMetrics, MetricsSummary } from '../api/types'
import './HomePage.css'

interface HomePageProps {
  selectedEvalId: string | null
}

type TabType = 'evaluations' | 'safe-harbor'

// A note is considered "failed" if LLM produced no predictions (0 TP and 0 FP)
// This typically happens due to API errors, expired tokens, etc.
function isFailedNote(file: FileMetrics): boolean {
  return file.true_positives === 0 && file.false_positives === 0
}

// Recalculate aggregate metrics from a list of file metrics
function calculateAggregateMetrics(files: FileMetrics[]): MetricsSummary {
  const totals = files.reduce(
    (acc, f) => ({
      true_positives: acc.true_positives + f.true_positives,
      false_positives: acc.false_positives + f.false_positives,
      false_negatives: acc.false_negatives + f.false_negatives,
    }),
    { true_positives: 0, false_positives: 0, false_negatives: 0 }
  )

  const precision = totals.true_positives + totals.false_positives > 0
    ? totals.true_positives / (totals.true_positives + totals.false_positives)
    : 0
  const recall = totals.true_positives + totals.false_negatives > 0
    ? totals.true_positives / (totals.true_positives + totals.false_negatives)
    : 0
  const f1 = precision + recall > 0
    ? (2 * precision * recall) / (precision + recall)
    : 0

  return {
    precision,
    recall,
    f1,
    ...totals,
  }
}

function Tabs({ activeTab, setActiveTab }: { activeTab: TabType; setActiveTab: (t: TabType) => void }) {
  return (
    <div className="tabs-container">
      <div className="tabs">
        <button className={`tab ${activeTab === 'evaluations' ? 'active' : ''}`} onClick={() => setActiveTab('evaluations')}>
          Evaluations
        </button>
        <button className={`tab ${activeTab === 'safe-harbor' ? 'active' : ''}`} onClick={() => setActiveTab('safe-harbor')}>
          Safe Harbor Notes
        </button>
      </div>
    </div>
  )
}

export default function HomePage({ selectedEvalId }: HomePageProps) {
  const [activeTab, setActiveTab] = useState<TabType>('evaluations')
  
  const { data: evaluation, isLoading: evalLoading } = useQuery({
    queryKey: ['evaluation', selectedEvalId],
    queryFn: () => getEvaluation(selectedEvalId!),
    enabled: !!selectedEvalId && activeTab === 'evaluations',
  })

  const { data: mistakes, isLoading: mistakesLoading } = useQuery({
    queryKey: ['mistakes', selectedEvalId],
    queryFn: () => getEvaluationMistakes(selectedEvalId!),
    enabled: !!selectedEvalId && activeTab === 'evaluations',
  })

  // Separate valid and failed notes
  const { validFiles, failedFiles, adjustedMetrics } = useMemo(() => {
    if (!evaluation) return { validFiles: [], failedFiles: [], adjustedMetrics: null }
    
    const valid = evaluation.per_file.filter(f => !isFailedNote(f))
    const failed = evaluation.per_file.filter(f => isFailedNote(f))
    
    // Recalculate metrics excluding failed notes
    const adjusted = valid.length > 0 ? calculateAggregateMetrics(valid) : null
    
    return { validFiles: valid, failedFiles: failed, adjustedMetrics: adjusted }
  }, [evaluation])

  if (activeTab === 'safe-harbor') {
    return (
      <div className="home-page">
        <Tabs activeTab={activeTab} setActiveTab={setActiveTab} />
        <SafeHarborNotes />
      </div>
    )
  }

  if (!selectedEvalId) {
    return (
      <div className="home-page">
        <Tabs activeTab={activeTab} setActiveTab={setActiveTab} />
        <div className="empty-state-large">
          <div className="empty-icon">📊</div>
          <h2>Select an Evaluation</h2>
          <p>Choose an evaluation run from the sidebar to view metrics and annotations.</p>
        </div>
      </div>
    )
  }

  if (evalLoading) {
    return (
      <div className="home-page">
        <Tabs activeTab={activeTab} setActiveTab={setActiveTab} />
        <div className="loading-state">Loading evaluation data...</div>
      </div>
    )
  }

  if (!evaluation) {
    return (
      <div className="home-page">
        <Tabs activeTab={activeTab} setActiveTab={setActiveTab} />
        <div className="error-state">Failed to load evaluation data.</div>
      </div>
    )
  }

  // Use adjusted metrics (excluding failed notes) if there are any failed notes
  const displayMetrics = failedFiles.length > 0 && adjustedMetrics ? adjustedMetrics : evaluation.aggregate

  return (
    <div className="home-page">
      <Tabs activeTab={activeTab} setActiveTab={setActiveTab} />
      <header className="page-header">
        <h1 className="page-title">Evaluation Overview</h1>
        <div className="eval-info">
          <span className="eval-mode">{evaluation.settings.evaluation_mode}</span>
          <span className="eval-files">{validFiles.length} files</span>
          {failedFiles.length > 0 && (
            <span className="eval-failed">{failedFiles.length} failed</span>
          )}
        </div>
      </header>
      
      {failedFiles.length > 0 && (
        <div className="failed-notes-banner">
          <span className="failed-icon">⚠</span>
          <span>
            {failedFiles.length} note{failedFiles.length !== 1 ? 's' : ''} excluded from statistics 
            (LLM produced no output — possible API error or expired token)
          </span>
        </div>
      )}
      
      <MetricsOverview metrics={displayMetrics} />
      <TypeBreakdownTable data={evaluation.by_type} />
      {mistakesLoading ? (
        <div className="loading-state">Loading mistakes...</div>
      ) : (
        <AnnotationList mistakes={mistakes || []} />
      )}
      
      {failedFiles.length > 0 && (
        <div className="failed-notes-section">
          <h2 className="section-title failed-title">
            <span className="failed-icon">⚠</span>
            Failed Notes ({failedFiles.length})
          </h2>
          <p className="failed-description">
            These notes had no LLM predictions (0 true positives and 0 false positives). 
            This typically indicates API errors, expired tokens, or processing failures.
          </p>
          <div className="failed-notes-list">
            {failedFiles.map(file => (
              <div key={file.file_id} className="failed-note-item">
                <span className="failed-note-name">{file.file_id}</span>
                <span className="failed-note-fn">{file.false_negatives} missed entities</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
