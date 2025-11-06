import React from 'react'
import { useParams } from 'react-router-dom'
import '../components/TrackDetailPage.css'

export type PlaylistInfo = {
  playlist_name: string;
  playlist_added_at?: string;
  position?: number;
}

export type TrackIdentity = {
  id: number;
  provider: string;
  provider_track_id: string;
  provider_url?: string;
  fingerprint?: string;
  created_at: string;
  updated_at: string;
}

export type Candidate = { 
  id: number; 
  track_id: number; 
  provider: string; 
  external_id: string; 
  url: string; 
  title: string; 
  channel?: string;
  score: number; 
  duration_sec?: number; 
  duration_delta_sec?: number; 
  chosen: boolean; 
  track?: TrackRead;
  score_breakdown?: { 
    artist: number; 
    title: number; 
    duration: number; 
    extended: number; 
    total: number; 
  } 
}

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
  release_date?: string | null
  downloaded_at?: string | null
  playlists?: PlaylistInfo[]
}

export const TrackDetailPage: React.FC = () => {
  const { id } = useParams()
  const trackId = id ? Number(id) : null
  
  const [track, setTrack] = React.useState<TrackRead | null>(null)
  const [identities, setIdentities] = React.useState<TrackIdentity[]>([])
  const [candidates, setCandidates] = React.useState<Candidate[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  
  // YouTube search state
  const [youtubeSearching, setYoutubeSearching] = React.useState(false)
  const [hideWeakResults, setHideWeakResults] = React.useState(true)
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set())

  // Utility functions
  const formatDuration = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('fr-FR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const getDisplayScore = (c: Candidate) => {
    const backendTotal = c.score_breakdown?.total
    
    // If backend total exists and is not zero, use it
    if (typeof backendTotal === 'number' && backendTotal !== 0) {
      return backendTotal
    }
    
    // Calculate total from individual components if available
    if (c.score_breakdown) {
      const calculatedTotal = 
        (c.score_breakdown.artist || 0) +
        (c.score_breakdown.title || 0) +
        (c.score_breakdown.duration || 0) +
        (c.score_breakdown.extended || 0)
      
      return calculatedTotal
    }
    
    // Fallback to the score field
    return typeof c.score === 'number' ? c.score : 0
  }

  const getRowKey = (c: Candidate) => `${c.id || 0}-${c.provider}-${c.external_id}`

  // Candidate action functions
  const chooseCandidate = async (candidateId: number) => {
    await fetch(`/api/v1/candidates/${candidateId}/choose`, { method: 'POST' })
    // Reload candidates (no auto-selection since user made manual choice)
    const candidatesResponse = await fetch(`/api/v1/candidates/enriched?track_id=${trackId}`)
    if (candidatesResponse.ok) {
      const candidatesData = await candidatesResponse.json()
      setCandidates(candidatesData)
    }
  }

  const downloadChosen = async (candidateId: number, trackId: number) => {
    // Choose this candidate and then force enqueue a download regardless of duplicates
    await fetch(`/api/v1/candidates/${candidateId}/choose`, { method: 'POST' })
    await fetch(`/api/v1/downloads/enqueue?track_id=${trackId}&candidate_id=${candidateId}&force=true`, { method: 'POST' })
    // Let user know; the Downloads page can show progress if needed
    window.dispatchEvent(new Event('downloads:changed'))
    alert('Download enqueued with manual override')
  }

  // YouTube search function
  const performYouTubeSearch = React.useCallback(async () => {
    if (!trackId || youtubeSearching) return
    
    setYoutubeSearching(true)
    console.log('Starting YouTube search for track:', trackId)
    
    try {
      // Fetch track info for logging (like in CandidatesPanel)
      const trackResponse = await fetch(`/api/v1/tracks/${trackId}`)
      const trackData = trackResponse.ok ? await trackResponse.json() : null

      const params = new URLSearchParams({ persist: 'true' })
      const searchUrl = `/api/v1/tracks/${trackId}/youtube/search?` + params.toString()
      console.log('Calling YouTube search endpoint:', searchUrl)
      
      const response = await fetch(searchUrl)
      
      if (!response.ok) {
        const msg = await response.text().catch(() => '')
        console.error('YouTube search failed:', response.status, msg)
        throw new Error(`Search failed (${response.status}). ${msg || ''}`)
      }

      const searchResults = await response.json().catch(() => null)
      console.log('YouTube search results:', searchResults)
      
      // Format and log the search query and results (like in CandidatesPanel)
      if (trackData && searchResults) {
        const formatDuration = (ms: number | null | undefined) => {
          if (!ms) return 'N/A'
          const totalSeconds = Math.floor(ms / 1000)
          const minutes = Math.floor(totalSeconds / 60)
          const seconds = totalSeconds % 60
          return `${minutes}:${seconds.toString().padStart(2, '0')}`
        }

        const logData = {
          query: {
            artists: trackData.artists || 'Unknown',
            title: trackData.title || 'Unknown',
            length: formatDuration(trackData.duration_ms)
          },
          candidates: Array.isArray(searchResults) ? searchResults.map((candidate: any, index: number) => ({
            id: `c${index + 1}`,
            channel: candidate.channel || 'Unknown',
            title: candidate.title || 'Unknown',
            length: candidate.duration_sec ? formatDuration(candidate.duration_sec * 1000) : 'N/A'
          })) : []
        }

        console.log(JSON.stringify(logData, null, 2))
      }
      
      console.log('Reloading candidates after search...')
      // Reload candidates after search using the enriched endpoint like in CandidatesPanel
      const candidatesResponse = await fetch(`/api/v1/candidates/enriched?track_id=${trackId}`)
      if (candidatesResponse.ok) {
        const candidatesData = await candidatesResponse.json()
        console.log('New candidates loaded:', candidatesData.length)
        
        // Auto-choose the highest scored candidate if none is chosen yet
        if (candidatesData.length > 0) {
          const hasChosenCandidate = candidatesData.some((c: any) => c.chosen)
          
          if (!hasChosenCandidate) {
            // Find the candidate with the highest score
            const highestScoreCandidate = candidatesData.reduce((best: any, current: any) => {
              const currentScore = getDisplayScore(current)
              const bestScore = getDisplayScore(best)
              return currentScore > bestScore ? current : best
            })
            
            // Auto-choose the highest scoring candidate
            if (highestScoreCandidate.id > 0) {
              await fetch(`/api/v1/candidates/${highestScoreCandidate.id}/choose`, { method: 'POST' })
              // Reload candidates to get updated chosen status
              const updatedResponse = await fetch(`/api/v1/candidates/enriched?track_id=${trackId}`)
              if (updatedResponse.ok) {
                const updatedData = await updatedResponse.json()
                setCandidates(updatedData)
              } else {
                setCandidates(candidatesData)
              }
            } else {
              setCandidates(candidatesData)
            }
          } else {
            setCandidates(candidatesData)
          }
        } else {
          setCandidates([])
        }
      } else {
        console.error('Failed to reload candidates:', candidatesResponse.status)
      }
      
      // Notify other components if needed
      window.dispatchEvent(new Event('candidates:changed'))
      console.log('YouTube search completed successfully')
    } catch (err) {
      console.error('YouTube search error:', err)
    } finally {
      setYoutubeSearching(false)
    }
  }, [trackId, youtubeSearching])

  React.useEffect(() => {
    const loadTrackDetails = async () => {
      if (!trackId) return
      setLoading(true)
      setError(null)
      
      try {
        // Load track with playlist info
        const trackResponse = await fetch(`/api/v1/tracks/with_playlist_info?track_id=${trackId}`)
        if (!trackResponse.ok) throw new Error('Failed to load track')
        const trackData = await trackResponse.json()
        if (trackData.length > 0) {
          setTrack(trackData[0])
        } else {
          setTrack(null)
        }

        // Load identities
        const identitiesResponse = await fetch(`/api/v1/tracks/${trackId}/identities`)
        if (identitiesResponse.ok) {
          const identitiesData = await identitiesResponse.json()
          setIdentities(identitiesData)
        } else {
          setIdentities([])
        }

        // Load candidates
        const candidatesResponse = await fetch(`/api/v1/candidates/enriched?track_id=${trackId}`)
        if (candidatesResponse.ok) {
          const candidatesData = await candidatesResponse.json()
          
          // Auto-choose the highest scored candidate if none is chosen yet
          if (candidatesData.length > 0) {
            const hasChosenCandidate = candidatesData.some((c: Candidate) => c.chosen)
            
            if (!hasChosenCandidate) {
              // Find the candidate with the highest score
              const highestScoreCandidate = candidatesData.reduce((best: Candidate, current: Candidate) => {
                const currentScore = getDisplayScore(current)
                const bestScore = getDisplayScore(best)
                return currentScore > bestScore ? current : best
              })
              
              // Auto-choose the highest scoring candidate
              if (highestScoreCandidate.id > 0) {
                await fetch(`/api/v1/candidates/${highestScoreCandidate.id}/choose`, { method: 'POST' })
                // Reload candidates to get updated chosen status
                const updatedResponse = await fetch(`/api/v1/candidates/enriched?track_id=${trackId}`)
                if (updatedResponse.ok) {
                  const updatedData = await updatedResponse.json()
                  setCandidates(updatedData)
                } else {
                  setCandidates(candidatesData)
                }
              } else {
                setCandidates(candidatesData)
              }
            } else {
              setCandidates(candidatesData)
            }
          } else {
            setCandidates([])
          }
        } else {
          setCandidates([])
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }

    loadTrackDetails()
  }, [trackId]) // Suppression de loadTrackDetails des dépendances

  if (loading) return <div>Loading track details...</div>
  if (error) return <div>Error: {error}</div>
  if (!track) return <div>Track not found</div>

  return (
    <div className="track-detail-page" key={trackId}>
      <h1>Track Details (ID: {trackId})</h1>
      
      {/* Track Overview */}
      <section className="track-overview">
        <h2>Track Information</h2>
        <div className="track-info-grid">
          <div className="track-main-info">
            <div className="track-cover">
              {track.cover_url && (
                <img src={track.cover_url} alt="Track cover" />
              )}
            </div>
            <div className="track-metadata">
              <h3>{track.title}</h3>
              <p><strong>Artists:</strong> {track.artists}</p>
              {track.album && <p><strong>Album:</strong> {track.album}</p>}
              {track.duration_ms && <p><strong>Duration:</strong> {formatDuration(track.duration_ms)}</p>}
              {track.genre && <p><strong>Genre:</strong> {track.genre}</p>}
              {track.bpm && <p><strong>BPM:</strong> {track.bpm}</p>}
              {track.year && <p><strong>Year:</strong> {track.year}</p>}
              {track.isrc && <p><strong>ISRC:</strong> {track.isrc}</p>}
              <p><strong>Explicit:</strong> {track.explicit ? 'Yes' : 'No'}</p>
            </div>
          </div>
          
          <div className="track-dates">
            <h4>Important Dates</h4>
            {track.release_date && (
              <p><strong>Release Date:</strong> {formatDate(track.release_date)}</p>
            )}
            {track.downloaded_at && (
              <p><strong>Downloaded:</strong> {formatDate(track.downloaded_at)}</p>
            )}
          </div>
        </div>

        {/* Playlists */}
        {track.playlists && track.playlists.length > 0 && (
          <div className="track-playlists">
            <h4>In Playlists</h4>
            <div className="playlists-list">
              {track.playlists.map((playlist) => (
                <div key={playlist.playlist_name} className="playlist-item">
                  <strong>{playlist.playlist_name}</strong>
                  {playlist.playlist_added_at && (
                    <span> (added {formatDate(playlist.playlist_added_at)})</span>
                  )}
                  {playlist.position !== undefined && (
                    <span> - position {playlist.position}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Track Identities */}
      <section className="track-identities">
        <h2>Track Identities</h2>
        {identities.length > 0 ? (
          <table className="identities-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Track ID</th>
                <th>URL</th>
                <th>Fingerprint</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {identities.map((identity) => (
                <tr key={identity.id}>
                  <td>{identity.provider}</td>
                  <td>{identity.provider_track_id}</td>
                  <td>
                    {identity.provider_url ? (
                      <a href={identity.provider_url} target="_blank" rel="noopener noreferrer">
                        View
                      </a>
                    ) : '-'}
                  </td>
                  <td>{identity.fingerprint || '-'}</td>
                  <td>{formatDate(identity.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No identities found for this track.</p>
        )}
      </section>

      {/* YouTube Search */}
      <section className="youtube-search">
        <h2>YouTube Search</h2>
        <div className="search-controls">
          <label>
            <input
              type="checkbox"
              checked={hideWeakResults}
              onChange={(e) => setHideWeakResults(e.target.checked)}
            />
            Hide weak results (score &lt; 50)
          </label>
          <button 
            onClick={performYouTubeSearch}
            disabled={youtubeSearching}
            className="search-button"
          >
            {youtubeSearching ? 'Searching...' : 'Search YouTube'}
          </button>
        </div>
        <p className="search-info">
          This will search YouTube for candidates matching this track and add them to the candidates list below.
        </p>
      </section>

      {/* Search Candidates */}
      <section className="track-candidates">
        <h2>Search Candidates</h2>
        {(() => {
          const filteredCandidates = hideWeakResults 
            ? candidates.filter(c => getDisplayScore(c) >= 50)
            : candidates
          
          return filteredCandidates.length > 0 ? (
            <table className="candidates-table">
              <thead>
                <tr>
                  <th>Chosen</th>
                  <th>Thumb</th>
                  <th>Title</th>
                  <th>Source</th>
                  <th>Score</th>
                  <th>Duration</th>
                  <th>Δ</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredCandidates.map((candidate) => {
                  const rowKey = getRowKey(candidate)
                  return (
                    <React.Fragment key={rowKey}>
                      <tr className={candidate.chosen ? 'chosen-row' : ''}>
                        <td>{candidate.chosen ? '★' : ''}</td>
                        <td>{renderThumbCell(candidate, expanded, setExpanded, rowKey)}</td>
                        <td title={candidate.title}>
                          <div className="candidate-title">
                            {candidate.title}
                          </div>
                          {candidate.channel && (
                            <div className="candidate-channel">
                              {candidate.channel}
                            </div>
                          )}
                          {candidate.score_breakdown && (
                            <div className="score-breakdown">
                              {renderBadge('Artist', candidate.score_breakdown.artist)}
                              {renderBadge('Title', candidate.score_breakdown.title)}
                              {renderBadge('Duration', candidate.score_breakdown.duration)}
                              {renderBadge('Extended', candidate.score_breakdown.extended)}
                            </div>
                          )}
                        </td>
                        <td>{renderSourceCell(candidate, expanded, setExpanded, rowKey)}</td>
                        <td>{getDisplayScore(candidate).toFixed(2)}</td>
                        <td>{candidate.duration_sec != null ? formatHMS(candidate.duration_sec) : '-'}</td>
                        <td>{renderSignedDelta(track?.duration_ms || null, candidate.duration_sec, candidate.duration_delta_sec)}</td>
                        <td>
                          {!candidate.chosen && candidate.id > 0 && (
                            <button onClick={() => chooseCandidate(candidate.id)}>Choose</button>
                          )}
                          {candidate.id > 0 && (
                            <button 
                              onClick={() => downloadChosen(candidate.id, candidate.track_id)} 
                              className="download-button"
                            >
                              Download
                            </button>
                          )}
                        </td>
                      </tr>
                      {expanded.has(rowKey) && candidate.provider === 'youtube' && (
                        <tr key={`exp-${rowKey}`}>
                          <td colSpan={8}>
                            {renderYouTubeEmbed(candidate)}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <p>No candidates found for this track.</p>
          )
        })()}
      </section>
    </div>
  )
}

// Utility functions from CandidatesPanel
function formatHMS(totalSeconds: number): string {
  const t = Math.max(0, Math.floor(totalSeconds))
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const s = t % 60
  const hh = String(h).padStart(2, '0')
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

function renderSignedDelta(trackDurationMs: number | null, candidateDurationSec?: number, fallbackDeltaSec?: number | null) {
  if (trackDurationMs == null) {
    if (fallbackDeltaSec == null) return '-'
    const sign = fallbackDeltaSec > 0 ? '+' : fallbackDeltaSec < 0 ? '-' : ''
    return sign + formatHMS(Math.abs(Math.round(fallbackDeltaSec)))
  }
  if (candidateDurationSec == null) return '-'
  const signed = Math.round(candidateDurationSec - trackDurationMs / 1000)
  const sign = signed > 0 ? '+' : signed < 0 ? '-' : ''
  return sign + formatHMS(Math.abs(signed))
}

function renderSourceCell(
  c: Candidate,
  expanded: Set<string>,
  setExpanded: React.Dispatch<React.SetStateAction<Set<string>>>,
  rowKey: string
) {
  if (c.provider === 'youtube') {
    const url = c.url || (c.external_id ? `https://www.youtube.com/watch?v=${c.external_id}` : '')
    const isOpen = expanded.has(rowKey)
    const toggle = () => setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(rowKey)) next.delete(rowKey); else next.add(rowKey)
      return next
    })
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        {url ? <a href={url} target='_blank' rel='noreferrer'>YouTube</a> : <span title='Missing URL'>YouTube</span>}
        <button onClick={toggle} title={isOpen ? 'Hide preview' : 'Show preview'} style={{ padding: '2px 6px' }}>{isOpen ? 'Hide' : 'Preview'}</button>
      </span>
    )
  }
  return c.url ? <a href={c.url} target='_blank' rel='noreferrer'>Link</a> : <span>-</span>
}

function renderYouTubeEmbed(c: Candidate) {
  const id = getYouTubeId(c)
  if (!id) return null
  const src = `https://www.youtube.com/embed/${id}`
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 8 }}>
      <div style={{ position: 'relative', width: '100%', maxWidth: 560, paddingTop: '56.25%', background: '#000' }}>
        <iframe
          src={src}
          title={c.title}
          allow='accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share'
          allowFullScreen
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0 }}
        />
      </div>
    </div>
  )
}

function getYouTubeId(c: Candidate): string | null {
  // Prefer explicit external_id if it looks like a YouTube id
  if (c.provider === 'youtube' && c.external_id) {
    const idFromExternal = extractYouTubeId(c.external_id)
    if (idFromExternal) return idFromExternal
  }
  // Try parsing from URL
  if (c.url) {
    const idFromUrl = extractYouTubeId(c.url)
    if (idFromUrl) return idFromUrl
  }
  return null
}

function extractYouTubeId(input: string): string | null {
  // Accept plain IDs (including short fake ids used in tests) and typical YouTube URLs
  // Common full-length IDs are 11 chars; our backend tests may use shorter, so be permissive: 6-15 word chars and hyphens/underscores
  const plainId = /^[A-Za-z0-9_-]{6,15}$/
  if (plainId.test(input)) return input

  try {
    const u = new URL(input)
    if (u.hostname.includes('youtu.be')) {
      const id = u.pathname.replace(/^\//, '')
      return id || null
    }
    if (u.hostname.includes('youtube.com')) {
      const v = u.searchParams.get('v')
      if (v) return v
      const m = u.pathname.match(/\/embed\/([A-Za-z0-9_-]{6,15})/)
      if (m) return m[1]
    }
  } catch {
    // not a URL; fall through
  }
  return null
}

function renderThumbCell(
  c: Candidate,
  expanded: Set<string>,
  setExpanded: React.Dispatch<React.SetStateAction<Set<string>>>,
  rowKey: string
) {
  if (c.provider !== 'youtube') return <span>-</span>
  const id = getYouTubeId(c)
  if (!id) return <span>-</span>
  const thumb = `https://i.ytimg.com/vi/${id}/hqdefault.jpg`
  const isOpen = expanded.has(rowKey)
  const toggle = () => setExpanded(prev => {
    const next = new Set(prev)
    if (next.has(rowKey)) next.delete(rowKey); else next.add(rowKey)
    return next
  })
  return (
    <img
      src={thumb}
      alt={c.title}
      title={isOpen ? 'Hide preview' : 'Show preview'}
      onClick={toggle}
      style={{ width: 96, height: 'auto', cursor: 'pointer', borderRadius: 4, display: 'block' }}
      loading='lazy'
    />
  )
}

function renderBadge(label: string, value: number) {
  const sign = value > 0 ? '+' : value < 0 ? '-' : ''
  const abs = Math.abs(value)
  const bg = value > 0 ? '#e6ffed' : value < 0 ? '#ffecec' : '#f2f2f2'
  const color = value > 0 ? '#036b26' : value < 0 ? '#a40000' : '#555'
  const title = `${label}: ${sign}${abs.toFixed(2)}`
  return (
    <span style={{ background: bg, color, borderRadius: 4, padding: '2px 6px', fontSize: 12 }} title={title}>
      {label}: {sign}{abs.toFixed(2)}
    </span>
  )
}

export default TrackDetailPage