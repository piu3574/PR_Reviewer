import { useState, useEffect } from 'react'
import { Bar } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip
} from 'chart.js'
import './App.css'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)

function App() {
  const [view, setView] = useState('analyze')
  const [prUrl, setPrUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [sourceFilter, setSourceFilter] = useState('all')
  const [severityFilter, setSeverityFilter] = useState('all')
  const [history, setHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const fetchHistory = async () => {
    setHistoryLoading(true)
    try {
      const res = await fetch('http://localhost:8000/history')
      const data = await res.json()
      setHistory(data.history)
    } catch (err) {
      console.error('Failed to load history', err)
    } finally {
      setHistoryLoading(false)
    }
  }

  useEffect(() => {
    if (view === 'history') fetchHistory()
  }, [view])

  const handleAnalyze = async () => {
    if (!prUrl.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    setSourceFilter('all')
    setSeverityFilter('all')

    try {
      const response = await fetch('http://localhost:8000/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pr_url: prUrl })
      })

      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || 'Analysis failed')
      }

      const data = await response.json()
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = (prId) => {
    window.open(`http://localhost:8000/report/${prId}`, '_blank')
  }

  const riskColor = (risk) => {
    if (risk === 'High') return '#ff5c7a'
    if (risk === 'Medium') return '#ffb84d'
    return '#3ddc97'
  }

  const scoreColor = (score) => {
    if (score < 6) return '#ff5c7a'
    if (score < 8) return '#ffb84d'
    return '#3ddc97'
  }

  const severityToRiskLabel = (sev) => {
    if (sev === 'high') return 'High'
    if (sev === 'medium') return 'Medium'
    return 'Low'
  }

  const filteredIssues = result
    ? result.issues.filter((issue) => {
        const sourceMatch = sourceFilter === 'all' || issue.source === sourceFilter
        const severityMatch = severityFilter === 'all' || issue.severity === severityFilter
        return sourceMatch && severityMatch
      })
    : []

  const chartData = result ? {
    labels: ['Quality', 'Maintainability'],
    datasets: [{
      data: [result.scores.quality_score, result.scores.maintainability_score],
      backgroundColor: [
        scoreColor(result.scores.quality_score),
        scoreColor(result.scores.maintainability_score)
      ],
      borderRadius: 6,
      maxBarThickness: 60
    }]
  } : null

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: { min: 0, max: 10, ticks: { color: '#8b949e' }, grid: { color: '#1c2129' } },
      x: { ticks: { color: '#e6edf3' }, grid: { display: false } }
    }
  }

  return (
    <div className="app">
      <div className="glow-bg" />

      <div className="nav-tabs">
        <button className={view === 'analyze' ? 'active' : ''} onClick={() => setView('analyze')}>
          Analyze
        </button>
        <button className={view === 'history' ? 'active' : ''} onClick={() => setView('history')}>
          History
        </button>
      </div>

      {view === 'analyze' && (
        <>
          <div className="hero">
            <span className="badge">✦ Static Analysis + AI Reasoning</span>
            <h1>Review Pull Requests<br />Before They Break Things</h1>
            <p className="subtitle">
              Paste a GitHub PR link. Get a scored, structured review in seconds.
            </p>

            <div className="input-bar">
              <span className="prompt-symbol">$</span>
              <input
                type="text"
                placeholder="paste a github pull request link..."
                value={prUrl}
                onChange={(e) => setPrUrl(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
              />
              <button onClick={handleAnalyze} disabled={loading}>
                {loading ? 'Analyzing...' : 'Analyze'}
              </button>
            </div>

            {loading && (
              <p className="status-text">
                Fetching PR, running static analysis, calling AI reviewer... this can take up to 30s.
              </p>
            )}

            {error && <p className="error-text">Error: {error}</p>}

            {!result && !loading && (
              <div className="quickstart">
                <span className="quickstart-label">Try an example:</span>
                <button className="chip" onClick={() => setPrUrl('https://github.com/piu3574/test-repo/pull/1')}>
                  Python PR
                </button>
                <button className="chip" onClick={() => setPrUrl('https://github.com/piu3574/test-repo/pull/2')}>
                  JavaScript PR
                </button>
              </div>
            )}

            {!result && !loading && (
              <div className="how-it-works">
                <div className="step">
                  <span className="step-num">01</span>
                  <h4>Fetch</h4>
                  <p>Pulls the PR's changed files and diff from GitHub.</p>
                </div>
                <div className="step">
                  <span className="step-num">02</span>
                  <h4>Analyze</h4>
                  <p>Runs static tools (pylint, bandit, eslint) plus an AI reviewer.</p>
                </div>
                <div className="step">
                  <span className="step-num">03</span>
                  <h4>Score & Report</h4>
                  <p>Produces a scorecard and a downloadable PDF report.</p>
                </div>
              </div>
            )}
          </div>

          {result && (
            <div className="results">
              <div className="pr-summary-card">
                <h2>{result.pr_title}</h2>
                <p className="meta">PR #{result.pr_id}</p>
              </div>

              <div className="results-top-grid">
                <div className="chart-card">
                  <Bar data={chartData} options={chartOptions} />
                </div>

                <div className="score-stack">
                  <div className="score-card">
                    <span className="score-label">Code Quality</span>
                    <span className="score-value" style={{ color: scoreColor(result.scores.quality_score) }}>
                      {result.scores.quality_score}/10
                    </span>
                  </div>
                  <div className="score-card">
                    <span className="score-label">Security Risk</span>
                    <span className="score-value" style={{ color: riskColor(result.scores.security_risk) }}>
                      {result.scores.security_risk}
                    </span>
                  </div>
                  <div className="score-card">
                    <span className="score-label">Maintainability</span>
                    <span className="score-value" style={{ color: scoreColor(result.scores.maintainability_score) }}>
                      {result.scores.maintainability_score}/10
                    </span>
                  </div>
                </div>
              </div>

              <button className="download-btn" onClick={() => handleDownload(result.pr_id)}>
                Download PDF Report
              </button>

              <div className="issues-list">
                <div className="issues-header">
                  <h3>Findings ({filteredIssues.length}{filteredIssues.length !== result.issues.length ? ` of ${result.issues.length}` : ''})</h3>

                  <div className="filters">
                    <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
                      <option value="all">All sources</option>
                      <option value="static">Static only</option>
                      <option value="ai">AI only</option>
                    </select>

                    <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
                      <option value="all">All severities</option>
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                  </div>
                </div>

                {filteredIssues.length === 0 && (
                  <p className="empty-state">No findings match the selected filters.</p>
                )}

                {filteredIssues.map((issue, idx) => (
                  <div key={idx} className="issue-row">
                    <span className={`source-tag ${issue.source}`}>{issue.source}</span>
                    <span className="issue-file">{issue.file_name}:{issue.line_number ?? '-'}</span>
                    <span className="issue-type">{issue.issue_type}</span>
                    <span
                      className="issue-severity"
                      style={{ color: riskColor(severityToRiskLabel(issue.severity)) }}
                    >
                      {issue.severity.toUpperCase()}
                    </span>
                    <p className="issue-desc">{issue.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {view === 'history' && (
        <div className="history-view">
          <h1>Past Analyses</h1>
          {historyLoading && <p className="status-text">Loading history...</p>}
          {!historyLoading && history.length === 0 && (
            <p className="empty-state">No PRs analyzed yet. Go to the Analyze tab to get started.</p>
          )}
          {history.map((item) => (
            <div key={item.pr_id} className="history-row">
              <div className="history-info">
                <h3>{item.title}</h3>
                <p className="meta">{item.repo_name} #{item.pr_number} · by {item.author}</p>
              </div>
              <div className="history-scores">
                <span style={{ color: scoreColor(item.quality_score) }}>Q: {item.quality_score ?? '-'}</span>
                <span style={{ color: riskColor(item.security_risk) }}>{item.security_risk ?? '-'}</span>
                <span style={{ color: scoreColor(item.maintainability_score) }}>M: {item.maintainability_score ?? '-'}</span>
              </div>
              <button className="download-btn-small" onClick={() => handleDownload(item.pr_id)}>
                Download PDF
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default App