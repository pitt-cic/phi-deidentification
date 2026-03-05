import { useState } from 'react'
import type { TypeMetrics } from '../api/types'
import './TypeBreakdownTable.css'

interface TypeBreakdownTableProps {
  data: TypeMetrics[]
}

type SortKey = 'type_name' | 'precision' | 'recall' | 'f1' | 'true_positives' | 'false_positives' | 'false_negatives'
type SortDir = 'asc' | 'desc'

export default function TypeBreakdownTable({ data }: TypeBreakdownTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('false_negatives')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sortedData = [...data].sort((a, b) => {
    const aVal = a[sortKey]
    const bVal = b[sortKey]
    const cmp = typeof aVal === 'string'
      ? aVal.localeCompare(bVal as string)
      : (aVal as number) - (bVal as number)
    return sortDir === 'asc' ? cmp : -cmp
  })

  const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`

  const SortIcon = ({ column }: { column: SortKey }) => {
    if (sortKey !== column) return <span className="sort-icon">⇅</span>
    return <span className="sort-icon active">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  return (
    <div className="type-breakdown">
      <h2 className="section-title">Metrics by Entity Type</h2>
      <div className="table-container">
        <table className="breakdown-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('type_name')}>
                Type <SortIcon column="type_name" />
              </th>
              <th onClick={() => handleSort('precision')}>
                Precision <SortIcon column="precision" />
              </th>
              <th onClick={() => handleSort('recall')}>
                Recall <SortIcon column="recall" />
              </th>
              <th onClick={() => handleSort('f1')}>
                F1 <SortIcon column="f1" />
              </th>
              <th onClick={() => handleSort('true_positives')}>
                TP <SortIcon column="true_positives" />
              </th>
              <th onClick={() => handleSort('false_positives')}>
                FP <SortIcon column="false_positives" />
              </th>
              <th onClick={() => handleSort('false_negatives')}>
                FN <SortIcon column="false_negatives" />
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedData.map(row => (
              <tr key={row.type_name} className={row.f1 < 1 ? 'has-errors' : ''}>
                <td className="type-cell">
                  <span className="type-badge">{row.type_name}</span>
                </td>
                <td>{formatPercent(row.precision)}</td>
                <td>{formatPercent(row.recall)}</td>
                <td className="f1-cell">
                  <span className={`f1-value ${row.f1 >= 0.95 ? 'good' : row.f1 >= 0.9 ? 'ok' : 'poor'}`}>
                    {formatPercent(row.f1)}
                  </span>
                </td>
                <td className="count-cell tp">{row.true_positives.toLocaleString()}</td>
                <td className="count-cell fp">{row.false_positives > 0 ? row.false_positives.toLocaleString() : '—'}</td>
                <td className="count-cell fn">{row.false_negatives > 0 ? row.false_negatives.toLocaleString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
