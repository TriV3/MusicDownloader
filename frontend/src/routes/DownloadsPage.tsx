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
  track_title?: string
  track_artists?: string
}

export const DownloadsPage: React.FC = () => {
  const [items, setItems] = React.useState<Download[]>([])
  const [loading, setLoading] = React.useState(false)
  const [enqueueTrackId, setEnqueueTrackId] = React.useState('')
  const [enqueueCandidateId, setEnqueueCandidateId] = React.useState('')
  const [trackQuery, setTrackQuery] = React.useState('')
  const [trackOptions, setTrackOptions] = React.useState<any[]>([])
  const [includeDownloaded, setIncludeDownloaded] = React.useState(false)
  const [ready, setReady] = React.useState<any[]>([])
  const [loadingReady, setLoadingReady] = React.useState(false)

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/v1/downloads/with_tracks?limit=30')
      if (!r.ok) return
      setItems(await r.json())
      // Auto-cleanup old downloads (keep only 30 most recent)
      fetch('/api/v1/downloads/cleanup', { method: 'POST' }).catch(() => {})
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => { load() }, [load])
  // Removed continuous 1.5s polling. Use the Refresh buttons to update manually.
  // Optional scaffold if you later want a toggle:
  // const [autoRefresh, setAutoRefresh] = React.useState(false)
  // React.useEffect(() => {
  //   if (!autoRefresh) return
  //   const id = setInterval(load, 5000)
  //   return () => clearInterval(id)
  // }, [autoRefresh, load])
  const loadReady = React.useCallback(async () => {
    setLoadingReady(true)
    try {
      const r = await fetch('/api/v1/tracks/ready_for_download?include_downloaded=' + (includeDownloaded ? 'true' : 'false'))
      if (!r.ok) return
      setReady(await r.json())
    } finally {
      setLoadingReady(false)
    }
  }, [includeDownloaded])

  React.useEffect(() => {
    loadReady()
  }, [loadReady])

  // Lookup tracks by text (title/artists)
  const searchTracks = React.useCallback(async () => {
    if (!trackQuery || trackQuery.length < 2) { setTrackOptions([]); return }
    const r = await fetch('/api/v1/tracks?q=' + encodeURIComponent(trackQuery) + '&limit=10')
    if (r.ok) setTrackOptions(await r.json())
  }, [trackQuery])
  React.useEffect(() => { const id = setTimeout(searchTracks, 250); return () => clearTimeout(id) }, [trackQuery, searchTracks])

  const enqueueTrack = async (trackId: number) => {
    const r = await fetch('/api/v1/downloads/enqueue?track_id=' + trackId, { method: 'POST' })
    if (r.ok) {
      load(); loadReady()
    }
  }

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

  const cancelDownload = async (id: number) => {
    const r = await fetch(`/api/v1/downloads/cancel/${id}`, { method: 'POST' })
    if (r.ok) {
      load()
      return
    }
    if (r.status === 409) {
      alert('This job is already running and cannot be cancelled.')
      load()
      return
    }
    alert('Cancel failed: ' + r.status)
  }

  const stopAllDownloads = async () => {
    if (!confirm('Stop all downloads? Queued downloads will be marked as skipped.')) return
    try {
      const r = await fetch('/api/v1/downloads/stop_all', { method: 'POST' })
      if (r.ok) {
        const data = await r.json()
        alert(`Stopped successfully!\nQueued downloads skipped: ${data.queued_skipped}\nWorker stopped: ${data.worker_stopped}`)
        load()
      } else {
        alert('Failed to stop downloads: ' + r.status)
      }
    } catch (e) {
      console.error('Stop all error:', e)
      alert('Error stopping downloads')
    }
  }

  const restartWorker = async () => {
    if (!confirm('Restart the download worker? This will stop current downloads and restart the worker.')) return
    try {
      const r = await fetch('/api/v1/downloads/restart_worker', { method: 'POST' })
      if (r.ok) {
        alert('Download worker restarted successfully!')
        load()
      } else {
        alert('Failed to restart worker: ' + r.status)
      }
    } catch (e) {
      console.error('Restart worker error:', e)
      alert('Error restarting worker')
    }
  }

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ margin: 0 }}>Downloads</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={stopAllDownloads} style={{ background: '#f44336', color: 'white', border: 'none', padding: '8px 16px', borderRadius: 4, cursor: 'pointer' }}>
            Stop All Downloads
          </button>
          <button onClick={restartWorker} style={{ background: '#ff9800', color: 'white', border: 'none', padding: '8px 16px', borderRadius: 4, cursor: 'pointer' }}>
            Restart Worker
          </button>
        </div>
      </div>
      <div style={{ border: '1px solid #ddd', padding: 10, borderRadius: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <h3 style={{ margin: 0 }}>Ready to download</h3>
          <button onClick={loadReady} disabled={loadingReady}>{loadingReady ? 'Loading…' : 'Refresh'}</button>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
          <thead>
            <tr style={{ textAlign: 'left' }}>
              <th>Track ID</th>
              <th>Title</th>
              <th>Artists</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {ready.map((t: any) => (
              <tr key={t.id}>
                <td>{t.id}</td>
                <td>{t.title}</td>
                <td>{t.artists}</td>
                <td><button onClick={() => enqueueTrack(t.id)}>Enqueue</button></td>
              </tr>
            ))}
            {ready.length === 0 && <tr><td colSpan={4} style={{ textAlign: 'center', padding: 8 }}>No tracks ready</td></tr>}
          </tbody>
        </table>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ position: 'relative', display: 'inline-block' }}>
          <div style={{ fontSize: 12, color: '#666' }}>Find track</div>
          <input placeholder='Type title or artist' value={trackQuery} onChange={e => setTrackQuery(e.target.value)} style={{ minWidth: 240 }} />
          {trackOptions.length > 0 && (
            <div style={{ border: '1px solid #ddd', maxHeight: 180, overflow: 'auto', background: '#fff', position: 'absolute', zIndex: 1, top: '100%', left: 0, right: 0 }}>
              {trackOptions.map((t: any) => (
                <div key={t.id} style={{ padding: 6, cursor: 'pointer' }} onClick={() => { setEnqueueTrackId(String(t.id)); setTrackOptions([]); setTrackQuery(`${t.artists} - ${t.title}`) }}>
                  {t.artists} - {t.title}
                </div>
              ))}
            </div>
          )}
        </div>
        <input placeholder='Candidate ID (optional)' value={enqueueCandidateId} onChange={e => setEnqueueCandidateId(e.target.value)} />
        <button onClick={enqueue} disabled={!enqueueTrackId}>Enqueue</button>
        <button onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <input type='checkbox' checked={includeDownloaded} onChange={e => setIncludeDownloaded(e.target.checked)} /> Include downloaded
        </label>
      </div>
      <div style={{ border: '1px solid #ddd', borderRadius: 6, overflow: 'hidden' }}>
        <h3 style={{ margin: 0, padding: 12, background: '#f5f5f5', borderBottom: '1px solid #ddd' }}>Recent Downloads (Last 30)</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', background: '#fafafa' }}>
              <th style={{ padding: '8px 12px', borderBottom: '1px solid #ddd' }}>Track</th>
              <th style={{ padding: '8px 12px', borderBottom: '1px solid #ddd' }}>Status</th>
              <th style={{ padding: '8px 12px', borderBottom: '1px solid #ddd' }}>Time</th>
              <th style={{ padding: '8px 12px', borderBottom: '1px solid #ddd' }}>Error</th>
              <th style={{ padding: '8px 12px', borderBottom: '1px solid #ddd' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map(d => {
              const statusColor = d.status === 'done' ? '#4caf50' : d.status === 'failed' ? '#f44336' : d.status === 'running' ? '#2196f3' : d.status === 'already' ? '#9e9e9e' : '#ff9800'
              const canCancel = d.status === 'queued'
              return (
                <tr key={d.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '8px 12px' }}>
                    <div style={{ fontWeight: 500 }}>{d.track_artists ?? 'Unknown'}</div>
                    <div style={{ fontSize: '0.9em', color: '#666' }}>{d.track_title ?? 'Unknown Title'}</div>
                    <div style={{ fontSize: '0.85em', color: '#999' }}>Track #{d.track_id}</div>
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <span style={{ 
                      padding: '4px 8px', 
                      borderRadius: 4, 
                      background: statusColor + '20',
                      color: statusColor,
                      fontSize: '0.9em',
                      fontWeight: 500
                    }}>
                      {d.status}
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px', fontSize: '0.9em', color: '#666' }}>
                    {d.finished_at ? new Date(d.finished_at).toLocaleString() : 
                     d.started_at ? new Date(d.started_at).toLocaleString() : 
                     new Date(d.created_at).toLocaleString()}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    {d.error_message ? (
                      <div style={{ 
                        color: '#f44336',
                        fontSize: '0.9em',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        maxWidth: 500
                      }}>
                        {d.error_message}
                      </div>
                    ) : '-'}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    {canCancel && (
                      <button 
                        onClick={() => cancelDownload(d.id)}
                        style={{ 
                          background: '#f44336', 
                          color: 'white', 
                          border: 'none', 
                          padding: '4px 12px', 
                          borderRadius: 4, 
                          cursor: 'pointer',
                          fontSize: '0.85em'
                        }}
                      >
                        Cancel
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
            {items.length === 0 && (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: 20, color: '#999' }}>
                  No downloads yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default DownloadsPage
