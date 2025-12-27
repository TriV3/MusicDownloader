import React from 'react'
import '../styles/dashboard.css'

type PlaylistStat = {
  playlist_id: number | null
  name: string
  provider: string
  total_tracks: number
  downloaded_tracks: number
  not_downloaded_tracks: number
  searched_not_found?: number
}

export const DashboardPage: React.FC = () => {
  const [stats, setStats] = React.useState<PlaylistStat[] | null>(null)
  const [statsError, setStatsError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState<Record<string, string | null>>({})
  const [syncing, setSyncing] = React.useState(false)
  const [syncResult, setSyncResult] = React.useState<string | null>(null)
  const [accountId, setAccountId] = React.useState<number | null>(null)
  const burstRef = React.useRef<number>(0)
  const statsRef = React.useRef<PlaylistStat[] | null>(null)

  // Ensure we have a Spotify account ID for sync
  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch('/api/v1/oauth/spotify/ensure_account', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
        if (r.ok) {
          const acc = await r.json()
          setAccountId(acc.id)
        }
      } catch {}
    })()
  }, [])

  React.useEffect(() => {
    let cancelled = false
    const load = () => {
      fetch('/api/v1/playlists/stats?selected_only=true')
        .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
        .then((d: PlaylistStat[]) => { if (!cancelled) { setStats(d); statsRef.current = d } })
        .catch((e) => { if (!cancelled) setStatsError(String(e)) })
    }
    // initial
    load()
    // poll: while any playlist has pending, refresh every 5s (lighter)
    const iv = setInterval(() => {
      const current = statsRef.current || []
      const pending = current.some((s: PlaylistStat) => s.not_downloaded_tracks > 0)
      const now = Date.now()
      const inBurst = burstRef.current > now
      if (pending || inBurst) load()
    }, 5000)
    return () => { cancelled = true; clearInterval(iv) }
  }, [])
  const sorted = React.useMemo(() => {
    const list = stats ? [...stats] : null
    if (!list) return null
    // Sort by priority: pending first (descending), then not_found (descending), keep 'Other' last
    list.sort((a, b) => {
      const aOther = a.playlist_id == null
      const bOther = b.playlist_id == null
      if (aOther && !bOther) return 1
      if (!aOther && bOther) return -1
      
      // First sort by pending tracks (not_downloaded_tracks)
      const pendingDiff = b.not_downloaded_tracks - a.not_downloaded_tracks
      if (pendingDiff !== 0) return pendingDiff
      
      // Then by not found tracks
      const aNotFound = a.searched_not_found || 0
      const bNotFound = b.searched_not_found || 0
      const notFoundDiff = bNotFound - aNotFound
      if (notFoundDiff !== 0) return notFoundDiff
      
      // Finally by name
      return a.name.localeCompare(b.name)
    })
    return list
  }, [stats])

  const syncPlaylists = async (force: boolean = false) => {
    if (!accountId) {
      setSyncResult('No Spotify account configured')
      return
    }
    setSyncing(true)
    setSyncResult(null)
    try {
      const forceParam = force ? '&force=true' : ''
      const r = await fetch(`/api/v1/playlists/spotify/sync?account_id=${accountId}${forceParam}`, { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' } 
      })
      if (!r.ok) {
        let errDetail = ''
        try { errDetail = (await r.json()).detail } catch { errDetail = await r.text() }
        setSyncResult(`Sync failed (${r.status}): ${errDetail.substring(0, 180)}`)
        return
      }
      let data: any = {}
      try { data = await r.json() } catch { data = {} }
      if (typeof data.total_tracks_created === 'number') {
        setSyncResult(`Created ${data.total_tracks_created}, Updated ${data.total_tracks_updated}, Linked ${data.total_links_created}, Removed ${data.total_links_removed || 0}`)
      } else {
        setSyncResult('Sync completed')
      }
      // Refresh stats after sync
      fetch('/api/v1/playlists/stats?selected_only=true')
        .then(r => r.json())
        .then((d: PlaylistStat[]) => { setStats(d); statsRef.current = d })
        .catch(() => {})
      // Notify other components to refresh their data
      window.dispatchEvent(new CustomEvent('tracks:changed'))
    } catch (e: any) {
      setSyncResult('Sync error: ' + (e?.message || e))
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <h2 style={{ marginTop: 0 }}>Dashboard</h2>
      <section style={{ display: 'grid', gap: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: '12px 0 4px' }}>Playlists — Pending downloads</h3>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              className="pl-btn"
              onClick={(e) => syncPlaylists(e.ctrlKey || e.metaKey)}
              disabled={syncing || !accountId}
              title="Sync selected Spotify playlists to get new tracks (Ctrl+Click to force full sync)"
            >
              {syncing ? 'Syncing…' : 'Sync playlists'}
            </button>
            <span className="pl-hint">(Ctrl+Click: force)</span>
            {syncResult && <span className="pl-note">{syncResult}</span>}
            <button
              className="pl-btn"
              onClick={async () => {
                try {
                  const r = await fetch('/api/v1/downloads/stop_all', { method: 'POST' })
                  if (!r.ok) throw new Error(await r.text())
                } catch (e) {
                  // ignore visual error; button is best-effort
                } finally {
                  // force refresh after stop
                  fetch('/api/v1/playlists/stats?selected_only=true').then(r => r.json()).then((d: PlaylistStat[]) => setStats(d)).catch(() => {})
                }
              }}
            >Stop all</button>
          </div>
        </div>
        {statsError && <div style={{ color: 'crimson' }}>Failed to load stats: {statsError}</div>}
        {!sorted && !statsError && <div>Loading…</div>}
        {sorted && sorted.length === 0 && <div>No playlists selected yet.</div>}
        {sorted && sorted.length > 0 && (
          <div className="pl-list">
            {sorted.map((s: PlaylistStat) => (
              <div key={(s.playlist_id ?? 'other') + '-' + s.name} className="pl-row">
                <div className="pl-meta">
                  <span className="pl-name">{s.name}</span>
                  <span className="pl-provider">[{s.provider}]</span>
                </div>
                <div className="pl-center">
                  {/* progress bar */}
                  {s.total_tracks > 0 ? (
                    <div className="pl-progress" aria-label={`Progress for ${s.name}`}>
                      {(() => {
                        const pct = Math.max(0, Math.min(100, Math.round((s.downloaded_tracks / s.total_tracks) * 100)))
                        return (
                          <>
                            <div className="pl-progress-bar" style={{ width: pct + '%' }} />
                            <div className="pl-progress-text">{pct}%</div>
                          </>
                        )
                      })()}
                    </div>
                  ) : (
                    <div className="pl-note">No tracks.</div>
                  )}
                  <div className="pl-counters">
                    <span title="Not downloaded">Pending: {s.not_downloaded_tracks}</span>
                    {typeof s.searched_not_found === 'number' && s.searched_not_found > 0 && (
                      <span title="Searched but not found">Not found: {s.searched_not_found}</span>
                    )}
                    <span title="Already in library">Downloaded: {s.downloaded_tracks}</span>
                    <span title="Total tracks in playlist">Total: {s.total_tracks}</span>
                  </div>
                </div>
                <div className="pl-actions">
                  {s.playlist_id && (
                    <>
                      <button
                        onClick={async () => {
                          const key = String(s.playlist_id)
                          setBusy(prev => ({ ...prev, [key]: 'Starting…' }))
                          try {
                            const r = await fetch(`/api/v1/playlists/${s.playlist_id}/auto_download`, { method: 'POST' })
                            if (!r.ok) throw new Error(await r.text())
                            const summary = await r.json()
                            // API now returns immediately with status "processing"
                            const msg = summary.status === 'processing' 
                              ? `Processing ${summary.total_tracks} tracks in background…`
                              : `Queued ${summary.enqueued || 0} / ${summary.total_tracks || 0}`
                            setBusy(prev => ({ ...prev, [key]: msg }))
                            // force a refresh now that jobs are queued
                            fetch('/api/v1/playlists/stats?selected_only=true').then(r => r.json()).then((d: PlaylistStat[]) => setStats(d)).catch(() => {})
                            // enable short burst polling (2s) for ~20s
                            burstRef.current = Date.now() + 20000
                          } catch (e: any) {
                            setBusy(prev => ({ ...prev, [key]: `Error: ${String(e?.message || e)}` }))
                          } finally {
                            setTimeout(() => setBusy(prev => ({ ...prev, [key]: null })), 2500)
                          }
                        }}
                        className="pl-btn"
                        disabled={s.not_downloaded_tracks === 0}
                        title={s.not_downloaded_tracks === 0 ? 'No pending tracks to download' : 'Download all pending tracks'}
                      >Download</button>
                      
                      {typeof s.searched_not_found === 'number' && s.searched_not_found > 0 && (
                        <button
                          onClick={async () => {
                            const key = `retry-${s.playlist_id}`
                            setBusy(prev => ({ ...prev, [key]: 'Retrying…' }))
                            try {
                              const r = await fetch(`/api/v1/playlists/${s.playlist_id}/retry_not_found`, { method: 'POST' })
                              if (!r.ok) throw new Error(await r.text())
                              const summary = await r.json()
                              const msg = summary.status === 'processing'
                                ? `Retrying ${summary.retry_tracks} tracks in background…`
                                : `Retried ${summary.retry_tracks || 0}`
                              setBusy(prev => ({ ...prev, [key]: msg }))
                              fetch('/api/v1/playlists/stats?selected_only=true').then(r => r.json()).then((d: PlaylistStat[]) => setStats(d)).catch(() => {})
                              burstRef.current = Date.now() + 20000
                            } catch (e: any) {
                              setBusy(prev => ({ ...prev, [key]: `Error: ${String(e?.message || e)}` }))
                            } finally {
                              setTimeout(() => setBusy(prev => ({ ...prev, [key]: null })), 2500)
                            }
                          }}
                          className="pl-btn"
                          title={`Retry searching for ${s.searched_not_found} not found tracks`}
                        >Retry Not Found</button>
                      )}
                    </>
                  )}
                  {s.playlist_id && (busy[String(s.playlist_id)] || busy[`retry-${s.playlist_id}`]) && (
                    <span className="pl-note">{busy[String(s.playlist_id)] || busy[`retry-${s.playlist_id}`]}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

export default DashboardPage
