import React from 'react'
import { Link } from 'react-router-dom'
import { useAudioPlayer } from '../contexts/AudioPlayerContext'
import type { NormalizationPreview } from './NormalizationPlayground'
import { userPreferences } from '../services/userPreferences'
import './AudioPlayer.css'

export type PlaylistInfo = {
  playlist_id: number;
  playlist_name: string;
  playlist_added_at?: string;
  position?: number;
}

export type TrackRead = {
  id: number
  title: string
  artists: string
  album?: string | null
  duration_ms?: number | null
  actual_duration_ms?: number | null  // Actual duration from downloaded file
  isrc?: string | null
  year?: number | null
  explicit: boolean
  cover_url?: string | null
  normalized_title: string
  normalized_artists: string
  genre?: string | null
  bpm?: number | null
  release_date?: string | null
  downloaded_at?: string | null
  playlists?: PlaylistInfo[]
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
  const [filterDurationMin, setFilterDurationMin] = React.useState('') // in format M:SS
  const [filterDurationMax, setFilterDurationMax] = React.useState('') // in format M:SS
  const [filterActualDurationMin, setFilterActualDurationMin] = React.useState('') // in format M:SS
  const [filterActualDurationMax, setFilterActualDurationMax] = React.useState('') // in format M:SS
  // Removed audio feature filters (tempo, energy, danceability)
  const [filterCreatedFrom, setFilterCreatedFrom] = React.useState('') // date input (YYYY-MM-DD)
  const [filterCreatedTo, setFilterCreatedTo] = React.useState('')

  // Column visibility state - initialize from localStorage
  const [showIdColumn, setShowIdColumn] = React.useState(() => userPreferences.getTrackColumnsVisibility().showIdColumn)
  const [showPosColumn, setShowPosColumn] = React.useState(() => userPreferences.getTrackColumnsVisibility().showPositionColumn)
  const [showDownloadedColumn, setShowDownloadedColumn] = React.useState(() => userPreferences.getTrackColumnsVisibility().showDownloadedColumn)
  const [showGenreColumn, setShowGenreColumn] = React.useState(() => userPreferences.getTrackColumnsVisibility().showGenreColumn)
  const [showBpmColumn, setShowBpmColumn] = React.useState(() => userPreferences.getTrackColumnsVisibility().showBpmColumn)
  const [showDurationColumn, setShowDurationColumn] = React.useState(() => userPreferences.getTrackColumnsVisibility().showDurationColumn)
  const [showSpotifyAddedColumn, setShowSpotifyAddedColumn] = React.useState(() => userPreferences.getTrackColumnsVisibility().showSpotifyAddedColumn)
  const [showPlaylistAddedColumn, setShowPlaylistAddedColumn] = React.useState(() => userPreferences.getTrackColumnsVisibility().showPlaylistAddedColumn)
  const [showPlaylistsColumn, setShowPlaylistsColumn] = React.useState(() => userPreferences.getTrackColumnsVisibility().showPlaylistsColumn)
  const [showColumnMenu, setShowColumnMenu] = React.useState(false)

  // Sorting state
  // Default: playlist_added desc (most recent first)
  const [spotifyAddedAsc, setSpotifyAddedAsc] = React.useState<boolean | null>(null)
  const [playlistAddedAsc, setPlaylistAddedAsc] = React.useState<boolean | null>(false) // false = descending (most recent first)
  const [durationAsc, setDurationAsc] = React.useState<boolean | null>(null) // null = no sorting, true = ascending, false = descending
  const [actualDurationAsc, setActualDurationAsc] = React.useState<boolean | null>(null) // null = no sorting, true = ascending, false = descending

  const loadingRef = React.useRef(false)
  // Removed mountedRef pattern to avoid suppressing legitimate late responses; rely on aborting fetches instead if needed.
  const loadTracks = React.useCallback(async () => {
    if (loadingRef.current) return
    loadingRef.current = true
    setReloading(true)
    try {
      if (selectedPlaylistId === 'all') {
        const r = await fetch('/api/v1/tracks/with_playlist_info?limit=10000')
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
        // Enrich tracks with playlist_added_at from entries
        const trackList = entries.map((e: any) => ({
          ...e.track,
          playlists: [{
            playlist_id: selectedPlaylistId,
            playlist_name: playlists.find(p => p.id === selectedPlaylistId)?.name || 'Unknown',
            playlist_added_at: e.added_at,
            position: e.position
          }]
        }))
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

  // Save column visibility preferences whenever they change
  React.useEffect(() => {
    userPreferences.setTrackColumnsVisibility({
      showIdColumn,
      showPositionColumn: showPosColumn,
      showDownloadedColumn,
      showGenreColumn,
      showBpmColumn,
      showDurationColumn,
      showSpotifyAddedColumn,
      showPlaylistAddedColumn,
      showPlaylistsColumn,
    })
  }, [showIdColumn, showPosColumn, showDownloadedColumn, showGenreColumn, showBpmColumn, showDurationColumn, showSpotifyAddedColumn, showPlaylistAddedColumn, showPlaylistsColumn])

  // Debug helper removed (window.debugLoadTracks) now that loading is stable.

  // (Removed verbose debug logs now that rendering is stable)

  // Load library files to mark downloaded tracks
  const loadLibraryFlags = React.useCallback(async () => {
    try {
      const r = await fetch('/api/v1/library/files?limit=10000')
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

  const reindexLibrary = async () => {
    // Trigger server-side scan and metadata analysis to link files back to tracks
    try {
      const r = await fetch('/api/v1/library/files/scan', { method: 'POST' })
      if (r.ok) {
        try {
          const data = await r.json()
          let msg = `Library reindex completed\nDirectory: ${data.directory}\nScanned: ${data.scanned}\nMatched: ${data.matched}\nAdded: ${data.added}\nUpdated: ${data.updated}\nSkipped: ${data.skipped}`
          if (Array.isArray(data.skipped_files) && data.skipped_files.length > 0) {
            const list = data.skipped_files.slice(0, 20).join('\n - ')
            const more = data.skipped_files.length > 20 ? `\n(+ ${data.skipped_files.length - 20} more…)` : ''
            msg += `\n\nSkipped files:\n - ${list}${more}`
          }
          alert(msg)
        } catch {}
        // Refresh UI flags and track list
        loadTracks(); loadLibraryFlags()
        window.dispatchEvent(new CustomEvent('library:changed'))
      } else {
        const t = await r.text()
        alert('Reindex failed: ' + r.status + (t ? ('\n' + t) : ''))
      }
    } catch (e) {
      console.error('Reindex error', e)
    }
  }

  const reverseReindex = async () => {
    // Trigger reverse reindex: verify DB tracks against files on disk and link LibraryFile rows
    try {
      const r = await fetch('/api/v1/library/files/reindex_from_tracks', { method: 'POST' })
      if (r.ok) {
        try {
          const data = await r.json()
          let msg = `Reverse reindex completed\nDirectory: ${data.directory}\nFiles indexed: ${data.files_indexed}\nTracks checked: ${data.tracks_checked}\nTracks found: ${data.tracks_found}\nTracks missing: ${data.tracks_missing}\nLinked added: ${data.linked_added}\nLinked updated: ${data.linked_updated}`
          if (Array.isArray(data.missing_samples) && data.missing_samples.length > 0) {
            const list = data.missing_samples.slice(0, 10).map((m: any) => `#${m.id} ${m.artists} — ${m.title}`).join('\n - ')
            const more = data.missing_samples.length > 10 ? `\n(+ ${data.missing_samples.length - 10} more…)` : ''
            msg += `\n\nMissing samples:\n - ${list}${more}`
          }
          alert(msg)
        } catch {}
        // Refresh UI flags and track list
        loadTracks(); loadLibraryFlags()
        window.dispatchEvent(new CustomEvent('library:changed'))
      } else {
        const t = await r.text()
        alert('Reverse reindex failed: ' + r.status + (t ? ('\n' + t) : ''))
      }
    } catch (e) {
      console.error('Reverse reindex error', e)
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

  // Compute filtered and sorted tracks
  const filteredTracks = React.useMemo(() => {
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
    // Duration filter
    const parseDuration = (str: string): number | null => {
      const match = str.trim().match(/^(\d+):(\d{1,2})$/)
      if (!match) return null
      const minutes = parseInt(match[1], 10)
      const seconds = parseInt(match[2], 10)
      if (seconds >= 60) return null
      return (minutes * 60 + seconds) * 1000
    }
    if (filterDurationMin.trim()) {
      const minMs = parseDuration(filterDurationMin)
      if (minMs !== null) {
        derived = derived.filter(t => t.duration_ms != null && t.duration_ms >= minMs)
      }
    }
    if (filterDurationMax.trim()) {
      const maxMs = parseDuration(filterDurationMax)
      if (maxMs !== null) {
        derived = derived.filter(t => t.duration_ms != null && t.duration_ms <= maxMs)
      }
    }
    if (filterActualDurationMin.trim()) {
      const minMs = parseDuration(filterActualDurationMin)
      if (minMs !== null) {
        derived = derived.filter(t => t.actual_duration_ms != null && t.actual_duration_ms >= minMs)
      }
    }
    if (filterActualDurationMax.trim()) {
      const maxMs = parseDuration(filterActualDurationMax)
      if (maxMs !== null) {
        derived = derived.filter(t => t.actual_duration_ms != null && t.actual_duration_ms <= maxMs)
      }
    }
    if (filterCreatedFrom) {
      const from = new Date(filterCreatedFrom).getTime()
      derived = derived.filter(t => t.release_date && new Date(t.release_date).getTime() >= from)
    }
    if (filterCreatedTo) {
      const to = new Date(filterCreatedTo + 'T23:59:59').getTime()
      derived = derived.filter(t => t.release_date && new Date(t.release_date).getTime() <= to)
    }
    // Sorting logic
    if (spotifyAddedAsc !== null) {
      derived = [...derived].sort((a, b) => {
        const da = a.release_date ? new Date(a.release_date).getTime() : 0
        const db = b.release_date ? new Date(b.release_date).getTime() : 0
        if (da === 0 && db === 0) return 0
        if (da === 0) return 1
        if (db === 0) return -1
        return spotifyAddedAsc ? da - db : db - da
      })
    } else if (playlistAddedAsc !== null) {
      derived = [...derived].sort((a, b) => {
        const getEarliestPlaylistDate = (track: TrackRead) => {
          if (!track.playlists || track.playlists.length === 0) return null
          const dates = track.playlists
            .map(p => p.playlist_added_at)
            .filter(date => date)
            .map(date => new Date(date!).getTime())
          return dates.length > 0 ? Math.min(...dates) : null
        }
        const da = getEarliestPlaylistDate(a)
        const db = getEarliestPlaylistDate(b)
        if (da === null && db === null) return 0
        if (da === null) return 1
        if (db === null) return -1
        return playlistAddedAsc ? da - db : db - da
      })
    } else if (durationAsc !== null) {
      derived = [...derived].sort((a, b) => {
        const da = a.duration_ms ?? 0
        const db = b.duration_ms ?? 0
        if (da === 0 && db === 0) return 0
        if (da === 0) return 1
        if (db === 0) return -1
        return durationAsc ? da - db : db - da
      })
    } else if (actualDurationAsc !== null) {
      derived = [...derived].sort((a, b) => {
        const da = a.actual_duration_ms ?? 0
        const db = b.actual_duration_ms ?? 0
        if (da === 0 && db === 0) return 0
        if (da === 0) return 1
        if (db === 0) return -1
        return actualDurationAsc ? da - db : db - da
      })
    }
    return derived
  }, [tracks, filterId, filterArtists, filterTitle, filterGenre, filterPlaylistName, filterDownloaded, 
      filterDurationMin, filterDurationMax, filterActualDurationMin, filterActualDurationMax,
      filterCreatedFrom, filterCreatedTo, spotifyAddedAsc, playlistAddedAsc, durationAsc, actualDurationAsc,
      memberships, downloadedIds])

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
    <button onClick={reindexLibrary} title="Disk → DB: Scan the library folder and link files to existing tracks; also updates missing durations using ffprobe when available">Reindex Library (Disk → DB)</button>
    <button onClick={reverseReindex} title="Tracks → Disk: Verify tracks in DB against files on disk and link missing LibraryFile entries">Reverse Reindex (Tracks → Disk)</button>
        <div className="column-toggle-wrapper">
          <button className="column-toggle-button" onClick={() => setShowColumnMenu(!showColumnMenu)} title="Show/hide columns">
            ⚙️
          </button>
          {showColumnMenu && (
            <div className="column-toggle-menu">
              <label><input type="checkbox" checked={showIdColumn} onChange={e => setShowIdColumn(e.target.checked)} /> ID</label>
              <label><input type="checkbox" checked={showPosColumn} onChange={e => setShowPosColumn(e.target.checked)} /> Position</label>
              <label><input type="checkbox" checked={showDownloadedColumn} onChange={e => setShowDownloadedColumn(e.target.checked)} /> Downloaded</label>
              <label><input type="checkbox" checked={showGenreColumn} onChange={e => setShowGenreColumn(e.target.checked)} /> Genre</label>
              <label><input type="checkbox" checked={showBpmColumn} onChange={e => setShowBpmColumn(e.target.checked)} /> BPM</label>
              <label><input type="checkbox" checked={showDurationColumn} onChange={e => setShowDurationColumn(e.target.checked)} /> Duration</label>
              <label><input type="checkbox" checked={showSpotifyAddedColumn} onChange={e => setShowSpotifyAddedColumn(e.target.checked)} /> Spotify Added</label>
              <label><input type="checkbox" checked={showPlaylistAddedColumn} onChange={e => setShowPlaylistAddedColumn(e.target.checked)} /> Playlist Added</label>
              <label><input type="checkbox" checked={showPlaylistsColumn} onChange={e => setShowPlaylistsColumn(e.target.checked)} /> Playlists</label>
            </div>
          )}
        </div>
      </div>
      {preview && (
        <div style={{ marginBottom: 12, fontSize: 13, fontFamily: 'var(--font-mono)', background: 'var(--bg-secondary)', padding: 8, borderRadius: 'var(--radius-sm)' }}>
          <strong>Preview:</strong> {preview.normalized_artists} – {preview.normalized_title}
        </div>
      )}
      <table className="tracks-table">
        <thead>
          <tr style={{ textAlign: 'left' }}>
            {selectedPlaylistId !== 'all' && showPosColumn && <th>Pos</th>}
            {showIdColumn && <th>ID</th>}
            <th>DL</th>
            <th>Cover</th>
            <th>Artists</th>
            <th>Title</th>
            {showPlaylistsColumn && <th>Playlists</th>}
            {showGenreColumn && <th>Genre</th>}
            {showBpmColumn && <th>BPM</th>}
            {showDurationColumn && (
              <th>
                <button 
                  className={`sort-button ${durationAsc !== null ? 'active' : ''}`}
                  onClick={() => {
                    setSpotifyAddedAsc(null)
                    setPlaylistAddedAsc(null)
                    setDurationAsc(p => p === null ? false : (p ? false : true))
                  }} 
                  title='Click to toggle sort by duration'
                >
                  Duration {durationAsc === null ? '' : durationAsc ? '▲' : '▼'}
                </button>
              </th>
            )}
            <th title="Actual duration from downloaded file" className="col-actual-duration">
              <button 
                className={`sort-button ${actualDurationAsc !== null ? 'active' : ''}`}
                onClick={() => {
                  setSpotifyAddedAsc(null)
                  setPlaylistAddedAsc(null)
                  setDurationAsc(null)
                  setActualDurationAsc(p => p === null ? false : (p ? false : true))
                }} 
                title='Click to toggle sort by actual duration'
              >
                <span className="actual-duration-label">Actual<br/>Duration</span> {actualDurationAsc === null ? '' : actualDurationAsc ? '▲' : '▼'}
              </button>
            </th>
            {showSpotifyAddedColumn && (
              <th>
                <button 
                  className={`sort-button ${spotifyAddedAsc !== null ? 'active' : ''}`}
                  onClick={() => {
                    setPlaylistAddedAsc(null)
                    setDurationAsc(null)
                    setSpotifyAddedAsc(p => p === null ? false : (p ? false : true))
                  }} 
                  title='Click to toggle sort by Spotify library added date'
                >
                  Spotify Added {spotifyAddedAsc === null ? '' : spotifyAddedAsc ? '▲' : '▼'}
                </button>
              </th>
            )}
            {showPlaylistAddedColumn && (
              <th>
                <button 
                  className={`sort-button ${playlistAddedAsc !== null ? 'active' : ''}`}
                  onClick={() => {
                    setSpotifyAddedAsc(null)
                    setDurationAsc(null)
                    setPlaylistAddedAsc(p => p === null ? false : (p ? false : true))
                  }} 
                  title='Click to toggle sort by playlist added date'
                >
                  Playlist Added {playlistAddedAsc === null ? '' : playlistAddedAsc ? '▲' : '▼'}
                </button>
              </th>
            )}
            {showDownloadedColumn && <th>Downloaded</th>}
            <th>Actions</th>
          </tr>
          {/* Filter row */}
          <tr>
            {selectedPlaylistId !== 'all' && showPosColumn && <th />}
            {showIdColumn && <th><input value={filterId} onChange={e => setFilterId(e.target.value)} placeholder='ID' /></th>}
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
            {showPlaylistsColumn && <th><input value={filterPlaylistName} onChange={e => setFilterPlaylistName(e.target.value)} placeholder='Playlist' /></th>}
            {showGenreColumn && <th><input value={filterGenre} onChange={e => setFilterGenre(e.target.value)} placeholder='Genre' /></th>}
            {showBpmColumn && <th />}
            {showDurationColumn && (
              <th>
                <div className="filter-duration">
                  <input value={filterDurationMin} onChange={e => setFilterDurationMin(e.target.value)} placeholder='Min (M:SS)' />
                  <input value={filterDurationMax} onChange={e => setFilterDurationMax(e.target.value)} placeholder='Max (M:SS)' />
                </div>
              </th>
            )}
            <th>
              <div className="filter-duration">
                <input value={filterActualDurationMin} onChange={e => setFilterActualDurationMin(e.target.value)} placeholder='Min (M:SS)' />
                <input value={filterActualDurationMax} onChange={e => setFilterActualDurationMax(e.target.value)} placeholder='Max (M:SS)' />
              </div>
            </th>
            {showSpotifyAddedColumn && <th />}
            {showPlaylistAddedColumn && (
              <th>
                <div className="filter-dates">
                  <input type='date' value={filterCreatedFrom} onChange={e => setFilterCreatedFrom(e.target.value)} />
                  <input type='date' value={filterCreatedTo} onChange={e => setFilterCreatedTo(e.target.value)} />
                </div>
              </th>
            )}
            {showDownloadedColumn && <th />}
            <th>
              <button className="reset-button" onClick={() => {
                setFilterId(''); setFilterArtists(''); setFilterTitle(''); setFilterGenre(''); setFilterPlaylistName('');
                setFilterDownloaded('all');
                setFilterDurationMin(''); setFilterDurationMax('');
                setFilterActualDurationMin(''); setFilterActualDurationMax('');
                setFilterCreatedFrom(''); setFilterCreatedTo('');
              }}>Reset</button>
            </th>
          </tr>
        </thead>
        <tbody>
          {filteredTracks.map((t, idx) => {
            const entry = selectedPlaylistId === 'all' ? null : entriesByPlaylist.find(e => e.track.id === t.id)
            return (
            <tr key={t.id}>
              {selectedPlaylistId !== 'all' && showPosColumn && <td className="col-id">{entry?.position ?? (idx + 1)}</td>}
              {showIdColumn && <td className="col-id">{t.id}</td>}
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
              {showPlaylistsColumn && (
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
              )}
              {showGenreColumn && <td className="col-genre">{t.genre ?? '-'}</td>}
              {showBpmColumn && <td className="col-bpm">{t.bpm ?? '-'}</td>}
              {showDurationColumn && <td className="col-duration">{t.duration_ms != null ? formatDuration(t.duration_ms) : '-'}</td>}
              <td className="col-duration" title="Actual duration from downloaded file">
                {t.actual_duration_ms != null ? formatDuration(t.actual_duration_ms) : '-'}
              </td>
              {showSpotifyAddedColumn && <td className="col-dates">{t.release_date ? formatDate(t.release_date) : '-'}</td>}
              {showPlaylistAddedColumn && (
                <td className="col-dates">
                  {t.playlists && t.playlists.length > 0 ? (
                    t.playlists
                      .filter(p => p.playlist_added_at)
                      .map(p => formatDate(p.playlist_added_at!))
                      .join(', ') || '-'
                  ) : '-'}
                </td>
              )}
              {showDownloadedColumn && <td className="col-dates">{downloadedIds.has(t.id) ? 'Yes' : 'No'}</td>}
              <td className="col-actions">
                <Link to={`/tracks/${t.id}`}>View</Link>
                <button onClick={() => remove(t.id)}>Delete</button>
              </td>
            </tr>
            )})}
          {tracks.length === 0 && !lastNonEmptyRef.current && (
            <tr>
              <td colSpan={17} className="tracks-empty">
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
        <span>Showing: {filteredTracks.length} track(s){selectedPlaylistId !== 'all' ? ` (playlist filter ${selectedPlaylistId})` : ''}</span>
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
