import React from 'react'

type PlaylistStat = {
  playlist_id: number | null
  name: string
  provider: string
  total_tracks: number
  downloaded_tracks: number
  not_downloaded_tracks: number
}

export const DashboardPage: React.FC = () => {
  const [stats, setStats] = React.useState<PlaylistStat[] | null>(null)
  const [statsError, setStatsError] = React.useState<string | null>(null)
  React.useEffect(() => {
    // Only include selected playlists in stats by default
    fetch('/api/v1/playlists/stats?selected_only=true')
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then((d: PlaylistStat[]) => setStats(d))
      .catch((e) => setStatsError(String(e)))
  }, [])
  const sorted = React.useMemo(() => {
    const list = stats ? [...stats] : null
    if (!list) return null
    // Sort by highest pending first, keep 'Other' last
    list.sort((a, b) => {
      const aOther = a.playlist_id == null
      const bOther = b.playlist_id == null
      if (aOther && !bOther) return 1
      if (!aOther && bOther) return -1
      return (b.not_downloaded_tracks - a.not_downloaded_tracks) || a.name.localeCompare(b.name)
    })
    return list
  }, [stats])

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <h2 style={{ marginTop: 0 }}>Dashboard</h2>
      <section style={{ display: 'grid', gap: 8 }}>
        <h3 style={{ margin: '12px 0 4px' }}>Playlists — Pending downloads</h3>
        {statsError && <div style={{ color: 'crimson' }}>Failed to load stats: {statsError}</div>}
        {!sorted && !statsError && <div>Loading…</div>}
        {sorted && sorted.length === 0 && <div>No playlists selected yet.</div>}
        {sorted && sorted.length > 0 && (
          <div style={{ display: 'grid', gap: 6 }}>
            {sorted.map((s: PlaylistStat) => (
              <div key={(s.playlist_id ?? 'other') + '-' + s.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', border: '1px solid #eee', padding: '8px 12px', borderRadius: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 600 }}>{s.name}</span>
                  <span style={{ fontSize: 12, opacity: 0.6 }}>[{s.provider}]</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace' }}>
                  <span title="Not downloaded">Pending: {s.not_downloaded_tracks}</span>
                  <span title="Already in library">Downloaded: {s.downloaded_tracks}</span>
                  <span title="Total tracks in playlist">Total: {s.total_tracks}</span>
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
