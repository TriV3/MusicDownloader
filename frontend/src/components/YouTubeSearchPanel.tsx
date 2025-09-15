import React from 'react'
import { useParams } from 'react-router-dom'
import type { Candidate } from './CandidatesPanel'

type TransientCandidate = Candidate & { transient?: boolean }

export const YouTubeSearchPanel: React.FC = () => {
  const { id } = useParams()
  const trackId = id ? Number(id) : null
  const [preferExtended, setPreferExtended] = React.useState<boolean>(false)
  const [persist, setPersist] = React.useState<boolean>(true)
  const [loading, setLoading] = React.useState(false)
  const [results, setResults] = React.useState<TransientCandidate[]>([])

  const runSearch = async () => {
    if (trackId == null) return
    setLoading(true)
    try {
      const params = new URLSearchParams({ prefer_extended: String(preferExtended), persist: String(persist) })
      const r = await fetch(`/api/v1/tracks/${trackId}/youtube/search?` + params.toString())
      const data = await r.json()
      setResults(data)
      // If persisted, dispatch event so other panels (candidates) can refresh
      if (persist) {
        window.dispatchEvent(new Event('candidates:changed'))
      }
    } catch (e) {
      // noop
    } finally {
      setLoading(false)
    }
  }

  return (
    <section style={{ border: '1px solid #ddd', padding: 16, borderRadius: 8 }}>
      <h2>YouTube Search</h2>
      <p style={{ marginTop: 0, color: '#666' }}>Uses the current track details; no free-text query here.</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <input type='checkbox' checked={preferExtended} onChange={e => setPreferExtended(e.target.checked)} /> Prefer Extended/Club Mix
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <input type='checkbox' checked={persist} onChange={e => setPersist(e.target.checked)} /> Persist
        </label>
        <button disabled={trackId == null || loading} onClick={runSearch}>{loading ? 'Searching...' : 'Search'}</button>
      </div>
      {results.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left' }}>
              <th>Title</th>
              <th>Score</th>
              <th>Dur (s)</th>
              <th>Δ (s)</th>
            </tr>
          </thead>
          <tbody>
            {results.map(r => (
              <tr key={r.external_id + ':' + r.id}>
                <td style={{ maxWidth: 300, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={r.title}>{r.title}</td>
                <td>{r.score.toFixed(3)}</td>
                <td>{r.duration_sec ?? '-'}</td>
                <td>{r.duration_delta_sec != null ? r.duration_delta_sec.toFixed(2) : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {results.length === 0 && !loading && <p style={{ margin: 0, opacity: 0.7 }}>No results yet.</p>}
    </section>
  )
}

export default YouTubeSearchPanel
