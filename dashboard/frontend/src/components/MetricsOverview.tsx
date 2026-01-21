import type { MetricsSummary } from '../api/types'
import './MetricsOverview.css'

interface MetricsOverviewProps {
  metrics: MetricsSummary
}

export default function MetricsOverview({ metrics }: MetricsOverviewProps) {
  const formatPercent = (value: number) => `${(value * 100).toFixed(2)}%`
  const formatNumber = (value: number) => value.toLocaleString()

  return (
    <div className="metrics-overview">
      <div className="metrics-row">
        <div className="metric-card primary">
          <div className="metric-label">Precision</div>
          <div className="metric-value">{formatPercent(metrics.precision)}</div>
          <div className="metric-bar">
            <div 
              className="metric-bar-fill precision" 
              style={{ width: formatPercent(metrics.precision) }}
            />
          </div>
        </div>
        
        <div className="metric-card primary">
          <div className="metric-label">Recall</div>
          <div className="metric-value">{formatPercent(metrics.recall)}</div>
          <div className="metric-bar">
            <div 
              className="metric-bar-fill recall" 
              style={{ width: formatPercent(metrics.recall) }}
            />
          </div>
        </div>
        
        <div className="metric-card primary">
          <div className="metric-label">F1 Score</div>
          <div className="metric-value">{formatPercent(metrics.f1)}</div>
          <div className="metric-bar">
            <div 
              className="metric-bar-fill f1" 
              style={{ width: formatPercent(metrics.f1) }}
            />
          </div>
        </div>
      </div>

      <div className="metrics-row counts">
        <div className="metric-card count tp">
          <div className="count-icon">✓</div>
          <div className="count-content">
            <div className="metric-value">{formatNumber(metrics.true_positives)}</div>
            <div className="metric-label">True Positives</div>
          </div>
        </div>
        
        <div className="metric-card count fp">
          <div className="count-icon">⚠</div>
          <div className="count-content">
            <div className="metric-value">{formatNumber(metrics.false_positives)}</div>
            <div className="metric-label">False Positives</div>
          </div>
        </div>
        
        <div className="metric-card count fn">
          <div className="count-icon">✗</div>
          <div className="count-content">
            <div className="metric-value">{formatNumber(metrics.false_negatives)}</div>
            <div className="metric-label">False Negatives</div>
          </div>
        </div>
      </div>
    </div>
  )
}
