import React from 'react'
import { Link } from 'react-router-dom'
import { useAudioPlayer } from '../contexts/AudioPlayerContext'
import type { NormalizationPreview } from './NormalizationPlayground'
import './AudioPlayer.css'

export type TrackRead = {
  id: number
  title: string
  artists: string
  album?: string | null
  duration_ms?: number | null
  isrc?: string | null
  year?: number | null
  explicit: boolean
  cover_url?: string | null
  normalized_title: string
  normalized_artists: string
  genre?: string | null
  bpm?: number | null
  created_at: string
  updated_at: string
}

export const TrackManager: React.FC = () => {
  const { currentTrack, isPlaying, playTrack, togglePlayPause } = useAudioPlayer()
  const [tracks, setTracks] = React.useState<TrackRead[]>([])
  const [playlists, setPlaylists] = React.useState<Array<{ id: number; name: string }>>([])
  const [selectedPlaylistId, setSelectedPlaylistId] = React.useState<number | 'all'>('all')
  const [entriesByPlaylist, setEntriesByPlaylist] = React.useState<Array<{ position: number | null; added_at: string | null; track: TrackRead }>>([])
  const [downloadedIds, setDownloadedIds] = React.useState<Set<number>>(new Set())
  const [memberships, setMemberships] = React.useState<Record<number, Array<{ playlist_id: number; playlist_name: string; position: number | null }>>>({})
  const [rawArtists, setRawArtists] = React.useState('')
  const [rawTitle, setRawTitle] = React.useState('')
  const [preview, setPreview] = React.useState<NormalizationPreview | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [reloading, setReloading] = React.useState(false)
  // For debugging: remember last fetched count even if state becomes empty later
  const [lastFetchedCount, setLastFetchedCount] = React.useState<number>(0)
  const lastNonEmptyRef = React.useRef<TrackRead[] | null>(null)

  // Filtering state (client-side)
  const [filterId, setFilterId] = React.useState('')
  const [filterArtists, setFilterArtists] = React.useState('')
  const [filterTitle, setFilterTitle] = React.useState('')
  const [filterGenre, setFilterGenre] = React.useState('')
  const [filterPlaylistName, setFilterPlaylistName] = React.useState('')
  const [filterDownloaded, setFilterDownloaded] = React.useState<'all' | 'yes' | 'no'>('all')
  // Removed audio feature filters (tempo, energy, danceability)
  const [filterCreatedFrom, setFilterCreatedFrom] = React.useState('') // date input (YYYY-MM-DD)
  const [filterCreatedTo, setFilterCreatedTo] = React.useState('')

  // Sorting state
  // Default: most recent first (created_at descending)
  const [createdAsc, setCreatedAsc] = React.useState<boolean | null>(false)

  const loadingRef = React.useRef(false)
  // Removed mountedRef pattern to avoid suppressing legitimate late responses; rely on aborting fetches instead if needed.
  const loadTracks = React.useCallback(async () => {
    if (loadingRef.current) return
    loadingRef.current = true
    setReloading(true)
    try {
      if (selectedPlaylistId === 'all') {
        const r = await fetch('/api/v1/tracks/?limit=1000')
        if (!r.ok) throw new Error('tracks fetch failed')
        const data = await r.json()
  setEntriesByPlaylist([])
        if (Array.isArray(data)) {
          setLastFetchedCount(data.length)
          setTracks(data)
        } else {
          console.warn('Unexpected tracks response (not array)')
        }
        if (Array.isArray(data) && data.length > 0) {
          try {
            const mRes = await fetch('/api/v1/playlists/memberships', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ track_ids: data.map((t: any) => t.id) })
            })
            if (mRes.ok) {
              const m = await mRes.json()
              setMemberships(m)
            } else setMemberships({})
          } catch (e) { /* ignore memberships error */ }
        } else { setMemberships({}) }
      } else {
        const r = await fetch(`/api/v1/playlists/${selectedPlaylistId}/entries`)
        if (!r.ok) throw new Error('entries fetch failed')
        const entries = await r.json()
        if (!Array.isArray(entries)) {
          setEntriesByPlaylist([])
          setTracks([])
          setMemberships({})
          return
        }
        setEntriesByPlaylist(entries)
        const trackList = entries.map((e: any) => e.track)
        setLastFetchedCount(trackList.length)
        setTracks(trackList)
        if (trackList.length > 0) {
          try {
            const mRes = await fetch('/api/v1/playlists/memberships', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ track_ids: trackList.map((t: any) => t.id) })
            })
            if (mRes.ok) {
              const m = await mRes.json()
              setMemberships(m)
            } else setMemberships({})
          } catch { /* ignore */ }
        } else { setMemberships({}) }
      }
    } catch (err) {
      console.error('loadTracks error', err)
      setMemberships({})
      // Do NOT clear tracks here to observe if previous data persists
    } finally {
      setReloading(false)
      loadingRef.current = false
    }
  }, [selectedPlaylistId])

  const loadPlaylists = React.useCallback(async () => {
    try {
      const r = await fetch('/api/v1/playlists/?selected=true')
      if (!r.ok) return
      const d = await r.json()
      setPlaylists(d.map((p: any) => ({ id: p.id, name: p.name })))
    } catch {}
  }, [])

  React.useEffect(() => { loadTracks() }, [loadTracks])
  React.useEffect(() => { loadPlaylists() }, [loadPlaylists])

  // Debug helper removed (window.debugLoadTracks) now that loading is stable.

  // (Removed verbose debug logs now that rendering is stable)

  // Load library files to mark downloaded tracks
  const loadLibraryFlags = React.useCallback(async () => {
    try {
      const r = await fetch('/api/v1/library/files?limit=500')
      if (!r.ok) return
      const files = await r.json()
      const ids = new Set<number>()
      for (const f of files) {
        if (typeof f.track_id === 'number') ids.add(f.track_id)
      }
      setDownloadedIds(ids)
    } catch {}
  }, [])

  React.useEffect(() => { loadLibraryFlags() }, [loadLibraryFlags])

  // Removed automatic 3s polling to reduce backend load. Manual Refresh button or events trigger updates.
  // If needed for diagnostics, you could restore polling with a toggle state.
  // Example scaffold:
  // const [autoRefresh, setAutoRefresh] = React.useState(false)
  // React.useEffect(() => {
  //   if (!autoRefresh) return
  //   const id = setInterval(() => { loadTracks(); loadLibraryFlags() }, 5000)
  //   return () => clearInterval(id)
  // }, [autoRefresh, loadTracks, loadLibraryFlags])

  // Refresh when other parts of app signal changes
  React.useEffect(() => {
    const handler = () => { loadTracks(); loadLibraryFlags() }
    window.addEventListener('tracks:changed', handler)
    window.addEventListener('library:changed', handler)
    window.addEventListener('downloads:changed', handler)
    return () => {
      window.removeEventListener('tracks:changed', handler)
      window.removeEventListener('library:changed', handler)
      window.removeEventListener('downloads:changed', handler)
    }
  }, [loadTracks, loadLibraryFlags])

  // Live preview normalization
  React.useEffect(() => {
    if (!rawArtists && !rawTitle) { setPreview(null); return }
    const ctrl = new AbortController()
    const run = async () => {
      const params = new URLSearchParams({ artists: rawArtists, title: rawTitle })
      const r = await fetch('/api/v1/tracks/normalize/preview?' + params.toString(), { signal: ctrl.signal })
      if (!r.ok) return
      setPreview(await r.json())
    }
    const id = setTimeout(() => { run().catch(() => {}) }, 150)
    return () => { clearTimeout(id); ctrl.abort() }
  }, [rawArtists, rawTitle])

  const create = async () => {
    if (!rawArtists || !rawTitle) return
    setLoading(true)
    try {
      const payload = { artists: rawArtists, title: rawTitle }
      const r = await fetch('/api/v1/tracks/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      if (r.ok) {
        setRawArtists('')
        setRawTitle('')
        setPreview(null)
        loadTracks()
        window.dispatchEvent(new CustomEvent('tracks:changed'))
      }
    } finally {
      setLoading(false)
    }
  }

  const remove = async (id: number) => {
    if (!confirm('Delete track #' + id + ' ?')) return
    const r = await fetch('/api/v1/tracks/' + id, { method: 'DELETE' })
    if (r.status === 204) {
      loadTracks()
      window.dispatchEvent(new CustomEvent('tracks:changed'))
    }
  }

  const handlePlayTrack = async (track: TrackRead) => {
    // Check if track is already playing, toggle if so
    if (currentTrack?.id === track.id) {
      togglePlayPause()
      return
    }

    // Check if track has been downloaded (has audio file available)
    const isDownloaded = downloadedIds.has(track.id)
    if (!isDownloaded) {
      alert('Cette piste n\'a pas encore été téléchargée. Veuillez d\'abord la télécharger pour pouvoir l\'écouter.')
      return
    }

    // Use the streaming endpoint for this track
    const audioUrl = `/api/v1/library/stream/${track.id}`
    
    playTrack({
      id: track.id,
      title: track.title,
      artists: track.artists,
      duration_ms: track.duration_ms
    }, audioUrl)
  }

  return (
    <section>
      <div className="tracks-controls">
        <div>
          <label>Playlist:</label>
          <select value={selectedPlaylistId} onChange={e => setSelectedPlaylistId(e.target.value === 'all' ? 'all' : Number(e.target.value))}>
            <option value='all'>All</option>
            {playlists.map(pl => <option key={pl.id} value={pl.id}>{pl.name}</option>)}
          </select>
        </div>
        <input placeholder='Artists' value={rawArtists} onChange={e => setRawArtists(e.target.value)} style={{ flex: 1 }} />
        <input placeholder='Title' value={rawTitle} onChange={e => setRawTitle(e.target.value)} style={{ flex: 1 }} />
        <button disabled={!rawArtists || !rawTitle || loading} onClick={create}>Create</button>
        <button onClick={() => { loadTracks(); loadLibraryFlags() }} disabled={reloading}>{reloading ? 'Refreshing…' : 'Refresh'}</button>
      </div>
      {preview && (
        <div style={{ marginBottom: 12, fontSize: 13, fontFamily: 'var(--font-mono)', background: 'var(--bg-secondary)', padding: 8, borderRadius: 'var(--radius-sm)' }}>
          <strong>Preview:</strong> {preview.normalized_artists} – {preview.normalized_title}
        </div>
      )}
      <table className="tracks-table">
        <thead>
          <tr style={{ textAlign: 'left' }}>
            {selectedPlaylistId !== 'all' && <th>Pos</th>}
            <th>ID</th>
            <th>DL</th>
            <th>Cover</th>
            <th>Artists</th>
            <th>Title</th>
            <th>Playlists</th>
            {/* Removed Tempo / Energy / Dance columns */}
            <th>Genre</th>
            <th>BPM</th>
            <th>Duration</th>
            <th>
              <button 
                className={`sort-button ${createdAsc !== null ? 'active' : ''}`}
                onClick={() => setCreatedAsc(p => p === null ? false : (p ? false : true))} 
                title='Click to toggle sort by created date'
              >
                Created {createdAsc === null ? '' : createdAsc ? '▲' : '▼'}
              </button>
            </th>
            <th>Updated</th>
            <th>Actions</th>
          </tr>
          {/* Filter row */}
          <tr>
            {selectedPlaylistId !== 'all' && <th />}
            <th><input value={filterId} onChange={e => setFilterId(e.target.value)} placeholder='ID' /></th>
            <th>
              <select value={filterDownloaded} onChange={e => setFilterDownloaded(e.target.value as any)}>
                <option value='all'>All</option>
                <option value='yes'>Downloaded</option>
                <option value='no'>Not downloaded</option>
              </select>
            </th>
            <th />
            <th><input value={filterArtists} onChange={e => setFilterArtists(e.target.value)} placeholder='Artists' /></th>
            <th><input value={filterTitle} onChange={e => setFilterTitle(e.target.value)} placeholder='Title' /></th>
            <th><input value={filterPlaylistName} onChange={e => setFilterPlaylistName(e.target.value)} placeholder='Playlist' /></th>
            <th><input value={filterGenre} onChange={e => setFilterGenre(e.target.value)} placeholder='Genre' /></th>
            <th />
            <th />
            <th>
              <div className="filter-dates">
                <input type='date' value={filterCreatedFrom} onChange={e => setFilterCreatedFrom(e.target.value)} />
                <input type='date' value={filterCreatedTo} onChange={e => setFilterCreatedTo(e.target.value)} />
              </div>
            </th>
            <th />
            <th>
              <button className="reset-button" onClick={() => {
                setFilterId(''); setFilterArtists(''); setFilterTitle(''); setFilterGenre(''); setFilterPlaylistName('');
                setFilterDownloaded('all');
                setFilterCreatedFrom(''); setFilterCreatedTo('');
              }}>Reset</button>
            </th>
          </tr>
        </thead>
        <tbody>
          {(() => {
            // Derived filtering + sorting
            let derived = tracks
            if (filterId.trim()) {
              const asNum = Number(filterId.trim())
              if (!isNaN(asNum)) derived = derived.filter(t => t.id === asNum)
              else derived = derived.filter(t => String(t.id).includes(filterId.trim()))
            }
            if (filterArtists.trim()) {
              const q = filterArtists.toLowerCase()
              derived = derived.filter(t => t.artists.toLowerCase().includes(q))
            }
            if (filterTitle.trim()) {
              const q = filterTitle.toLowerCase()
              derived = derived.filter(t => t.title.toLowerCase().includes(q))
            }
            if (filterGenre.trim()) {
              const q = filterGenre.toLowerCase()
              derived = derived.filter(t => (t.genre || '').toLowerCase().includes(q))
            }
            if (filterPlaylistName.trim()) {
              const q = filterPlaylistName.toLowerCase()
              derived = derived.filter(t => {
                const m = memberships[t.id]
                if (!Array.isArray(m) || m.length === 0) return false
                return m.some(pl => pl.playlist_name.toLowerCase().includes(q))
              })
            }
            if (filterDownloaded !== 'all') {
              derived = derived.filter(t => filterDownloaded === 'yes' ? downloadedIds.has(t.id) : !downloadedIds.has(t.id))
            }
            // Explicit filter removed
            const parseNum = (v: string) => {
              const n = Number(v)
              return isNaN(n) ? null : n
            }
            // Removed tempo/energy/danceability filtering
            if (filterCreatedFrom) {
              const from = new Date(filterCreatedFrom + 'T00:00:00Z').getTime()
              derived = derived.filter(t => new Date(t.created_at).getTime() >= from)
            }
            if (filterCreatedTo) {
              const to = new Date(filterCreatedTo + 'T23:59:59Z').getTime()
              derived = derived.filter(t => new Date(t.created_at).getTime() <= to)
            }
            if (createdAsc !== null) {
              derived = [...derived].sort((a, b) => {
                const da = new Date(a.created_at).getTime()
                const db = new Date(b.created_at).getTime()
                return createdAsc ? da - db : db - da
              })
            }
            return derived.map((t, idx) => {
            const entry = selectedPlaylistId === 'all' ? null : entriesByPlaylist.find(e => e.track.id === t.id)
            return (
            <tr key={t.id}>
              {selectedPlaylistId !== 'all' && <td className="col-id">{entry?.position ?? (idx + 1)}</td>}
              <td className="col-id">{t.id}</td>
              <td className="col-downloaded">
                {downloadedIds.has(t.id) ? (
                  <button 
                    className={`track-play-button ${currentTrack?.id === t.id && isPlaying ? 'playing' : ''}`}
                    onClick={() => handlePlayTrack(t)}
                    title={currentTrack?.id === t.id && isPlaying ? 'Pause' : 'Play'}
                  >
                    {currentTrack?.id === t.id && isPlaying ? '⏸️' : '▶️'}
                  </button>
                ) : (
                  <span style={{ opacity: 0.3, fontSize: '0.75rem' }} title="Piste non téléchargée">—</span>
                )}
              </td>
              <td className="col-cover">
                {t.cover_url ? (
                  <img src={t.cover_url} alt="cover" />
                ) : (
                  <div className="no-image">No image</div>
                )}
              </td>
              <td className="col-artists">{t.artists}</td>
              <td className="col-title">{t.title}</td>
              <td className="col-playlists">
                {Array.isArray(memberships[t.id]) && memberships[t.id].length > 0 ? (
                  memberships[t.id].map(pl => (
                    <span key={`${t.id}-${pl.playlist_id}`} className="playlist-badge">
                      {pl.playlist_name}{pl.position != null ? `#${pl.position}` : ''}
                    </span>
                  ))
                ) : (
                  <span style={{ opacity: 0.4 }}>—</span>
                )}
              </td>
              <td className="col-genre">{t.genre ?? '-'}</td>
              <td className="col-bpm">{t.bpm ?? '-'}</td>
              <td className="col-duration">{t.duration_ms != null ? formatDuration(t.duration_ms) : '-'}</td>
              <td className="col-dates">{formatDate(t.created_at)}</td>
              <td className="col-dates">{formatDate(t.updated_at)}</td>
              <td className="col-actions">
                <Link to={`/tracks/${t.id}`}>View</Link>
                <button onClick={() => remove(t.id)}>Delete</button>
              </td>
            </tr>
            )})
          })()}
          {tracks.length === 0 && !lastNonEmptyRef.current && (
            <tr>
              <td colSpan={16} className="tracks-empty">
                <div>No tracks to display.</div>
                {lastFetchedCount > 0 && (
                  <div className="debug-info">
                    Debug: last fetch returned {lastFetchedCount} items but none are currently rendered.
                  </div>
                )}
                <div>
                  Selected playlist: <strong>{selectedPlaylistId === 'all' ? 'All' : selectedPlaylistId}</strong>. Try clicking Refresh. Check browser console for any errors after the fetch log lines.
                </div>
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div className="tracks-stats">
        <span>Showing: {tracks.length} track(s){selectedPlaylistId !== 'all' ? ` (playlist filter ${selectedPlaylistId})` : ''}</span>
        {lastFetchedCount !== tracks.length && (
          <span className="mismatch">Mismatch: fetched {lastFetchedCount} vs rendered {tracks.length}</span>
        )}
      </div>
    </section>
  )
}

export default TrackManager

function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString()
  } catch {
    return iso
  }
}
