import { useQuery } from '@tanstack/react-query'
import { getEvaluation, getEvaluationMistakes } from '../api/client'
import MetricsOverview from '../components/MetricsOverview'
import TypeBreakdownTable from '../components/TypeBreakdownTable'
import AnnotationList from '../components/AnnotationList'
import './HomePage.css'

interface HomePageProps {
  selectedEvalId: string | null
}

export default function HomePage({ selectedEvalId }: HomePageProps) {
  const { data: evaluation, isLoading: evalLoading } = useQuery({
    queryKey: ['evaluation', selectedEvalId],
    queryFn: () => getEvaluation(selectedEvalId!),
    enabled: !!selectedEvalId,
  })

  const { data: mistakes, isLoading: mistakesLoading } = useQuery({
    queryKey: ['mistakes', selectedEvalId],
    queryFn: () => getEvaluationMistakes(selectedEvalId!),
    enabled: !!selectedEvalId,
  })

  if (!selectedEvalId) {
    return (
      <div className="home-page">
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
        <div className="loading-state">Loading evaluation data...</div>
      </div>
    )
  }

  if (!evaluation) {
    return (
      <div className="home-page">
        <div className="error-state">Failed to load evaluation data.</div>
      </div>
    )
  }

  return (
    <div className="home-page">
      <header className="page-header">
        <h1 className="page-title">Evaluation Overview</h1>
        <div className="eval-info">
          <span className="eval-mode">{evaluation.settings.evaluation_mode}</span>
          <span className="eval-files">{evaluation.settings.num_files} files</span>
        </div>
      </header>

      <MetricsOverview metrics={evaluation.aggregate} />
      
      <TypeBreakdownTable data={evaluation.by_type} />
      
      {mistakesLoading ? (
        <div className="loading-state">Loading mistakes...</div>
      ) : (
        <AnnotationList mistakes={mistakes || []} />
      )}
    </div>
  )
}



