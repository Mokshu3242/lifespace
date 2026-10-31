const METRICS = [
  { key: 'safety', label: 'Safety' },
  { key: 'access', label: 'Access' },
  { key: 'movement', label: 'Movement' },
  { key: 'energy', label: 'Energy' },
]

/** Four scores Before → After, each with the reason it was measured that way. */
export default function ScoreCard({ scores, showAfter }) {
  if (!scores) return null
  const side = showAfter ? 'after' : 'before'
  const flags = scores[side].flags || []
  return (
    <div className="scorecard">
      {METRICS.filter((m) => scores.before[m.key]).map((m) => {
        const b = scores.before[m.key].score, a = scores.after[m.key].score
        const now = side === 'after' ? a : b
        const diff = a - b
        return (
          <div key={m.key} className="metric">
            <div className="metric-head">
              <span>{m.label}</span>
              <span className="nums">
                {b} → <strong>{a}</strong>
                {diff !== 0 && <span className={diff > 0 ? 'good' : 'worse'}> {diff > 0 ? '+' : ''}{diff}</span>}
              </span>
            </div>
            <div className="metric-bar">
              <span style={{ width: `${now}%` }} className={now >= 70 ? 'hi' : now >= 40 ? 'mid' : 'lo'} />
              <i style={{ left: `${b}%` }} title="Before" />
            </div>
            <p className="note">{scores[side][m.key].why}</p>
          </div>
        )
      })}
      {flags.length > 0 && (
        <details className="flags" open>
          <summary>Furniture can&apos;t fix these ({flags.length})</summary>
          <ul>{flags.map((f) => <li key={f}>{f}</li>)}</ul>
        </details>
      )}
    </div>
  )
}
