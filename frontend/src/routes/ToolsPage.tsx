import React from 'react'
import { NormalizationPlayground } from '../components/NormalizationPlayground'
import { Link } from 'react-router-dom'

type Candidate = { id: number; track_id: number; provider: string; url: string; title: string; channel?: string; duration_sec?: number; score: number }
type Identity = { id: number; track_id: number; provider: string; provider_track_id: string; provider_url?: string; fingerprint?: string; created_at?: string }

const CandidateExplorer: React.FC = () => {
  const [items, setItems] = React.useState<Candidate[]>([])
  const [query, setQuery] = React.useState('')
  const [loading, setLoading] = React.useState(false)

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/v1/candidates/')
      if (!r.ok) return
      const data = await r.json()
      setItems(data)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => { load() }, [load])

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter(c =>
      c.title.toLowerCase().includes(q) ||
      (c.channel?.toLowerCase().includes(q)) ||
      c.provider.toLowerCase().includes(q) ||
      String(c.track_id).includes(q)
    )
  }, [items, query])

  return (
    <section style={{ border: '1px solid #ddd', padding: 16, borderRadius: 8 }}>
      <h3>Candidate Explorer</h3>
      <p style={{ color: '#666', marginTop: 0 }}>Search across persisted candidates (does not trigger external lookups).</p>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <input placeholder='Filter candidates...' value={query} onChange={e => setQuery(e.target.value)} style={{ flex: 1 }} />
        <button onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left' }}>
            <th>ID</th>
            <th>Track</th>
            <th>Title</th>
            <th>Channel</th>
            <th>Dur (s)</th>
            <th>Score</th>
            <th>Provider</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(c => (
            <tr key={c.id}>
              <td>{c.id}</td>
              <td><Link to={`/tracks/${c.track_id}`}>#{c.track_id}</Link></td>
              <td><a href={c.url} target='_blank' rel='noreferrer'>{c.title}</a></td>
              <td>{c.channel ?? '-'}</td>
              <td>{c.duration_sec ?? '-'}</td>
              <td>{c.score.toFixed(2)}</td>
              <td>{c.provider}</td>
            </tr>
          ))}
          {filtered.length === 0 && <tr><td colSpan={7} style={{ textAlign: 'center', padding: 8 }}>No candidates</td></tr>}
        </tbody>
      </table>
    </section>
  )
}

const IdentitiesExplorer: React.FC = () => {
  const [items, setItems] = React.useState<Identity[]>([])
  const [query, setQuery] = React.useState('')
  const [loading, setLoading] = React.useState(false)

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/v1/identities/')
      if (!r.ok) return
      const data = await r.json()
      setItems(data)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => { load() }, [load])

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter(i =>
      i.provider.toLowerCase().includes(q) ||
      i.provider_track_id.toLowerCase().includes(q) ||
      (i.provider_url?.toLowerCase().includes(q)) ||
      (i.fingerprint?.toLowerCase().includes(q)) ||
      String(i.track_id).includes(q)
    )
  }, [items, query])

  return (
    <section style={{ border: '1px solid #ddd', padding: 16, borderRadius: 8 }}>
      <h3>Identities Explorer</h3>
      <p style={{ color: '#666', marginTop: 0 }}>Browse identities across all tracks. Use the track detail page to see identities for a specific track.</p>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <input placeholder='Filter identities…' value={query} onChange={e => setQuery(e.target.value)} style={{ flex: 1 }} />
        <button onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left' }}>
            <th>ID</th>
            <th>Track</th>
            <th>Provider</th>
            <th>Provider Track ID</th>
            <th>Fingerprint</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(i => (
            <tr key={i.id}>
              <td>{i.id}</td>
              <td><Link to={`/tracks/${i.track_id}/identities`}>#{i.track_id}</Link></td>
              <td>{i.provider}</td>
              <td>
                {i.provider_url
                  ? <a href={i.provider_url} target='_blank' rel='noreferrer'>{i.provider_track_id}</a>
                  : i.provider_track_id}
              </td>
              <td>{i.fingerprint ?? '-'}</td>
              <td>{i.created_at ? new Date(i.created_at).toLocaleString() : '-'}</td>
            </tr>
          ))}
          {filtered.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', padding: 8 }}>No identities</td></tr>}
        </tbody>
      </table>
    </section>
  )
}

export const ToolsPage: React.FC = () => {
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <h2>Tools</h2>
      <CandidateExplorer />
      <IdentitiesExplorer />
      <NormalizationPlayground />
    </div>
  )
}

export default ToolsPage
