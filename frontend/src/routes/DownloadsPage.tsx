import React from 'react'

type Download = {
  id: number
  track_id: number
  candidate_id?: number | null
  provider: string
  status: string
  filepath?: string | null
  format?: string | null
  bitrate_kbps?: number | null
  filesize_bytes?: number | null
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
}

export const DownloadsPage: React.FC = () => {
  const [items, setItems] = React.useState<Download[]>([])
  const [loading, setLoading] = React.useState(false)
  const [enqueueTrackId, setEnqueueTrackId] = React.useState('')
  const [enqueueCandidateId, setEnqueueCandidateId] = React.useState('')

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/v1/downloads/?limit=100')
      if (!r.ok) return
      setItems(await r.json())
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    load()
    const id = setInterval(load, 1500)
    return () => clearInterval(id)
  }, [load])

  const enqueue = async () => {
    const params = new URLSearchParams({ track_id: enqueueTrackId })
    if (enqueueCandidateId) params.set('candidate_id', enqueueCandidateId)
    const r = await fetch('/api/v1/downloads/enqueue?' + params.toString(), { method: 'POST' })
    if (r.ok) {
      setEnqueueTrackId('')
      setEnqueueCandidateId('')
      load()
    }
  }

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <h2>Downloads</h2>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input placeholder='Track ID' value={enqueueTrackId} onChange={e => setEnqueueTrackId(e.target.value)} />
        <input placeholder='Candidate ID (optional)' value={enqueueCandidateId} onChange={e => setEnqueueCandidateId(e.target.value)} />
        <button onClick={enqueue} disabled={!enqueueTrackId}>Enqueue</button>
        <button onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left' }}>
            <th>ID</th>
            <th>Track</th>
            <th>Candidate</th>
            <th>Status</th>
            <th>Started</th>
            <th>Finished</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {items.map(d => (
            <tr key={d.id}>
              <td>{d.id}</td>
              <td>{d.track_id}</td>
              <td>{d.candidate_id ?? '-'}</td>
              <td>{d.status}</td>
              <td>{d.started_at ? new Date(d.started_at).toLocaleTimeString() : '-'}</td>
              <td>{d.finished_at ? new Date(d.finished_at).toLocaleTimeString() : '-'}</td>
              <td style={{ color: '#b00' }}>{d.error_message ?? ''}</td>
            </tr>
          ))}
          {items.length === 0 && <tr><td colSpan={7} style={{ textAlign: 'center', padding: 8 }}>No downloads</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

export default DownloadsPage
