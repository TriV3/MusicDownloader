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
  const [libFiles, setLibFiles] = React.useState<any[]>([])
  const [libLoading, setLibLoading] = React.useState(false)
  const [libTrackId, setLibTrackId] = React.useState('')
  const [nowPlayingId, setNowPlayingId] = React.useState<number | null>(null)

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
  const r = await fetch('/api/v1/downloads/with_tracks?limit=100')
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

  const loadLibrary = React.useCallback(async () => {
    setLibLoading(true)
    try {
      const p = new URLSearchParams()
      if (libTrackId) p.set('track_id', libTrackId)
      const r = await fetch('/api/v1/library/files' + (p.toString() ? ('?' + p.toString()) : ''))
      if (!r.ok) return
      setLibFiles(await r.json())
    } finally {
      setLibLoading(false)
    }
  }, [libTrackId])

  React.useEffect(() => {
    loadLibrary()
  }, [loadLibrary])

  const deleteLibraryFile = async (id: number) => {
    if (!confirm('Delete library file #' + id + ' from disk?')) return
    const r = await fetch('/api/v1/library/files/' + id, { method: 'DELETE' })
    if (r.ok) {
      loadLibrary()
      // Also refresh downloads, since file presence may affect UI logic elsewhere
      load()
    }
  }

  const resyncLibrary = async () => {
    const r = await fetch('/api/v1/library/files/resync', { method: 'POST' })
    if (r.ok) {
      loadLibrary()
      window.dispatchEvent(new CustomEvent('library:changed'))
    } else {
      const t = await r.text()
      alert('Resync failed: ' + r.status + (t ? ('\n' + t) : ''))
    }
  }

  const scanLibrary = async () => {
    const r = await fetch('/api/v1/library/files/scan', { method: 'POST' })
    if (r.ok) {
      try {
        const data = await r.json()
        alert(`Scan completed\nDirectory: ${data.directory}\nScanned: ${data.scanned}\nMatched: ${data.matched}\nAdded: ${data.added}\nUpdated: ${data.updated}\nSkipped: ${data.skipped}`)
      } catch {}
      loadLibrary()
      window.dispatchEvent(new CustomEvent('library:changed'))
    } else {
      const t = await r.text()
      alert('Scan failed: ' + r.status + (t ? ('\n' + t) : ''))
    }
  }

  const playFile = (id: number) => {
    setNowPlayingId(id)
    // The <audio> element will pick up the new src and play; autoplay may be blocked
    // so user can click Play if needed.
  }

  const revealInExplorer = async (id: number) => {
    const r = await fetch(`/api/v1/library/files/${id}/reveal`, { method: 'POST' })
    if (!r.ok) {
      const msg = await r.text()
      alert('Reveal failed: ' + r.status + (msg ? ('\n' + msg) : ''))
    }
  }

  const copyPath = async (filepath: string) => {
    try {
      await navigator.clipboard.writeText(filepath)
      // optional: toast
    } catch {
      alert('Could not copy to clipboard. Here is the path:\n' + filepath)
    }
  }

  const bottomPad = nowPlayingId ? 104 : 0
  return (
    <div style={{ display: 'grid', gap: 12, paddingBottom: bottomPad }}>
      <h2>Downloads</h2>
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
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left' }}>
            <th>ID</th>
            <th>Track ID</th>
            <th>Title</th>
            <th>Artists</th>
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
              <td>{d.track_title ?? '-'}</td>
              <td>{d.track_artists ?? '-'}</td>
              <td>{d.candidate_id ?? '-'}</td>
              <td>{d.status}</td>
              <td>{d.started_at ? new Date(d.started_at).toLocaleTimeString() : '-'}</td>
              <td>{d.finished_at ? new Date(d.finished_at).toLocaleTimeString() : '-'}</td>
              <td>
                <div
                  style={{
                    color: '#b00',
                    maxWidth: 360,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={d.error_message ?? ''}
                >
                  {d.error_message ?? ''}
                </div>
              </td>
            </tr>
          ))}
          {items.length === 0 && <tr><td colSpan={9} style={{ textAlign: 'center', padding: 8 }}>No downloads</td></tr>}
        </tbody>
      </table>

      <div style={{ borderTop: '1px solid #eee', marginTop: 16, paddingTop: 12 }}>
        <h3 style={{ marginTop: 0 }}>Library Files</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
          <input
            placeholder='Filter by Track ID'
            value={libTrackId}
            onChange={e => setLibTrackId(e.target.value.replace(/[^0-9]/g, ''))}
            style={{ width: 160 }}
          />
          <button onClick={loadLibrary} disabled={libLoading}>{libLoading ? 'Loading…' : 'Refresh'}</button>
          <button onClick={resyncLibrary}>Resync</button>
          <button onClick={scanLibrary}>Scan folder</button>
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left' }}>
              <th>ID</th>
              <th>Track ID</th>
              <th>File</th>
              <th>Size</th>
              <th>Modified</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {libFiles.map((f: any) => (
              <tr key={f.id}>
                <td>{f.id}</td>
                <td>{f.track_id}</td>
                <td>
                  <div style={{ maxWidth: 480, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={f.filepath}>
                    {f.filepath}
                  </div>
                </td>
                <td>{typeof f.file_size === 'number' ? (f.file_size > 1024 * 1024 ? (f.file_size / (1024*1024)).toFixed(2) + ' MB' : (f.file_size / 1024).toFixed(1) + ' KB') : '-'}</td>
                <td>{f.file_mtime ? new Date(f.file_mtime).toLocaleString() : '-'}</td>
                <td style={{ display: 'flex', gap: 8 }}>
                  <button onClick={() => playFile(f.id)}>Play</button>
                  <a href={`/api/v1/library/files/${f.id}/download`} target="_blank" rel="noreferrer">Download</a>
                  <button onClick={() => revealInExplorer(f.id)}>Reveal</button>
                  <button onClick={() => copyPath(f.filepath)}>Copy path</button>
                  <button onClick={() => deleteLibraryFile(f.id)}>Delete</button>
                </td>
              </tr>
            ))}
            {libFiles.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', padding: 8 }}>No files</td></tr>}
          </tbody>
        </table>
      </div>
      {/* Now Playing bar (only when playing) */}
      {nowPlayingId != null && (
        <div style={{ position: 'fixed', left: 0, right: 0, bottom: 0, background: '#111', color: '#fff', padding: 8, zIndex: 1000, boxShadow: '0 -2px 8px rgba(0,0,0,0.3)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <div style={{ fontSize: 12, opacity: 0.8 }}>
              {`Now Playing • File #${nowPlayingId}`}
            </div>
            <button onClick={() => setNowPlayingId(null)} style={{ fontSize: 12 }}>Hide</button>
          </div>
          <audio
            key={nowPlayingId}
            controls
            style={{ width: '100%' }}
            src={`/api/v1/library/files/${nowPlayingId}/stream`}
            preload="metadata"
          />
        </div>
      )}
    </div>
  )
}

export default DownloadsPage
