import React from 'react'

// Minimal UI to discover and select Spotify playlists
// Assumptions: one Spotify SourceAccount exists (or user provides account id)

type Playlist = {
  id?: number
  provider: string
  name: string
  source_account_id?: number | null
  provider_playlist_id?: string | null
  description?: string | null
  owner?: string | null
  snapshot?: string | null
  selected?: boolean
}

const PlaylistsPage: React.FC = () => {
  const [accountId, setAccountId] = React.useState<number | undefined>()
  const [connected, setConnected] = React.useState<boolean | null>(null)
  const [discovered, setDiscovered] = React.useState<Playlist[]>([])
  const [persist, setPersist] = React.useState(true)
  const [loading, setLoading] = React.useState(false)
  const [selectedIds, setSelectedIds] = React.useState<string[]>([])
  const [authUrl, setAuthUrl] = React.useState<string | null>(null)
  const [busyAuth, setBusyAuth] = React.useState(false)
  const [syncing, setSyncing] = React.useState(false)
  const [lastSync, setLastSync] = React.useState<string | null>(null)

  // Ensure we have a Spotify account (backend will create if missing)
  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch('/api/v1/oauth/spotify/ensure_account', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
        if (!r.ok) { setConnected(false); return }
        const acc = await r.json()
        setAccountId(acc.id)
        // Try silent refresh to avoid prompting user again if refresh token is stored
        try {
          const rf = await fetch(`/api/v1/oauth/spotify/refresh?account_id=${acc.id}`, { method: 'POST' })
          if (rf.ok) {
            setConnected(true)
            await discover(acc.id)
          } else {
            // Attempt to parse JSON error; fallback to text
            let msg: string
            try { msg = (await rf.json()).detail || rf.statusText } catch { msg = await rf.text() }
            console.warn('Spotify refresh failed:', rf.status, msg)
            setConnected(false)
          }
        } catch (e) {
            console.warn('Spotify refresh exception', e)
            setConnected(false)
        }
      } catch {}
    })()
  }, [])

  const discover = async (id?: number) => {
    const aid = id ?? accountId
    if (!aid) return
    setLoading(true)
    try {
      const url = `/api/v1/playlists/spotify/discover?account_id=${aid}&persist=${persist ? 'true' : 'false'}`
      const r = await fetch(url)
      const data: Playlist[] = await r.json()
      setDiscovered(data)
      setSelectedIds(data.filter(p => p.selected).map(p => p.provider_playlist_id || '').filter(Boolean) as string[])
    } finally {
      setLoading(false)
    }
  }

  const toggle = (spId: string) => {
    setSelectedIds(prev => prev.includes(spId) ? prev.filter(x => x !== spId) : [...prev, spId])
  }

  const saveSelection = async () => {
    if (!accountId) return
    await fetch('/api/v1/playlists/spotify/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: accountId, playlist_ids: selectedIds })
    })
    // Refresh list to reflect selection flags
    await discover()
  }

  const startAuth = async () => {
    if (!accountId) return
    setBusyAuth(true)
    try {
      // Use absolute redirect_to so the backend callback redirects back to the frontend dev server (5173)
      const target = encodeURIComponent(`${window.location.origin}/playlists`)
      const r = await fetch(`/api/v1/oauth/spotify/authorize?account_id=${accountId}&redirect_to=${target}`)
      if (!r.ok) throw new Error(await r.text())
      const data = await r.json()
      setAuthUrl(data.authorize_url)
      // Open Spotify login in the same tab for clearer flow
      window.location.href = data.authorize_url
    } catch (e) {
      console.error(e)
    } finally {
      setBusyAuth(false)
    }
  }

  const syncSelected = async () => {
    if (!accountId) return
    setSyncing(true)
    try {
      const r = await fetch(`/api/v1/playlists/spotify/sync?account_id=${accountId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
      if (!r.ok) {
        let errDetail = ''
        try { errDetail = (await r.json()).detail } catch { errDetail = await r.text() }
        setLastSync(`Sync failed (${r.status}): ${errDetail.substring(0,180)}`)
        return
      }
      let data: any = {}
      try { data = await r.json() } catch { data = {} }
      if (typeof data.total_tracks_created === 'number') {
        setLastSync(`Created ${data.total_tracks_created}, Updated ${data.total_tracks_updated}, Linked ${data.total_links_created}`)
      } else {
        setLastSync('Sync completed (no summary fields)')
      }
    } catch (e:any) {
      setLastSync('Sync error: ' + (e?.message || e))
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <h2>Playlists</h2>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        {connected ? (
          <span style={{ color: 'green' }}>Connected to Spotify</span>
        ) : (
          <button onClick={startAuth} disabled={!accountId || busyAuth}>{busyAuth ? 'Opening Spotify…' : 'Connect to Spotify'}</button>
        )}
        <label>
          <input type='checkbox' checked={persist} onChange={e => setPersist(e.target.checked)} /> Persist
        </label>
        <button onClick={() => discover()} disabled={!accountId || loading}>{loading ? 'Loading…' : 'Discover from Spotify'}</button>
        <button onClick={saveSelection} disabled={!accountId}>Save selection</button>
        <button onClick={syncSelected} disabled={!accountId || syncing}>{syncing ? 'Syncing…' : 'Sync selected'}</button>
        {lastSync && <span style={{ marginLeft: 8, opacity: 0.8 }}>{lastSync}</span>}
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left' }}>
            <th style={{ width: 32 }}>Sel</th>
            <th>Name</th>
            <th>Owner</th>
            <th>ID</th>
            <th>Snapshot</th>
          </tr>
        </thead>
        <tbody>
          {discovered.map(p => {
            const spId = p.provider_playlist_id || ''
            const checked = selectedIds.includes(spId)
            return (
              <tr key={spId || p.id}>
                <td><input type='checkbox' checked={checked} onChange={() => toggle(spId)} /></td>
                <td>{p.name}</td>
                <td>{p.owner ?? '-'}</td>
                <td>{spId || '-'}</td>
                <td>{p.snapshot ?? '-'}</td>
              </tr>
            )
          })}
          {discovered.length === 0 && (
            <tr><td colSpan={5} style={{ textAlign: 'center', padding: 8, color: '#666' }}>No playlists discovered yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default PlaylistsPage
