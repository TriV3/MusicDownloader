import React from 'react'
import { useParams } from 'react-router-dom'

export type Candidate = { id: number; track_id: number; provider: string; external_id: string; url: string; title: string; score: number; duration_sec?: number; duration_delta_sec?: number; chosen: boolean; score_breakdown?: { text: number; duration: number; extended: number; channel: number; penalty: number; total: number; details?: { text_similarity?: number; duration_bonus?: number; extended_base?: number; extended_length_bonus?: number | null; channel_bonus?: number; tokens_penalty?: number; keywords_penalty?: number } } }

export const CandidatesPanel: React.FC = () => {
  const { id } = useParams()
  const selectedTrack = id ? Number(id) : null
  const [candidates, setCandidates] = React.useState<Candidate[]>([])
  const [sort, setSort] = React.useState<'score' | 'duration_delta'>('score')
  const [manual, setManual] = React.useState({ provider: 'youtube', external_id: '', url: '', title: '', duration_sec: '', score: '' })
  const [ytPreferExtended, setYtPreferExtended] = React.useState(true)
  const [ytPersist, setYtPersist] = React.useState(true)
  const [ytLoading, setYtLoading] = React.useState(false)
  const [ytStatus, setYtStatus] = React.useState<string>('')
  const [strict, setStrict] = React.useState(true)
  const MIN_SCORE = 0.5
  const [trackDurationMs, setTrackDurationMs] = React.useState<number | null>(null)
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set())

  const getDisplayScore = React.useCallback((c: Candidate) => {
    const total = c.score_breakdown?.total
    return typeof total === 'number' ? total : (typeof c.score === 'number' ? c.score : 0)
  }, [])

  const getRowKey = React.useCallback((c: Candidate) => `${c.id || 0}-${c.provider}-${c.external_id}`, [])

  const load = React.useCallback(() => {
    if (selectedTrack == null) { setCandidates([]); return }
    const params = new URLSearchParams({ track_id: String(selectedTrack), sort, prefer_extended: String(ytPreferExtended) })
    // Pass strict filter intent to the server so negatives are hidden there too
    if (strict) {
      params.set('min_score', String(MIN_SCORE))
    }
    fetch('/api/v1/candidates/?' + params.toString())
      .then(r => r.ok ? r.json() : [])
      .then(async (d: Candidate[]) => {
        return Array.isArray(d) ? d : []
      })
      .then((d: Candidate[]) => {
        const normalized = d.map(x => ({ ...x, id: x.id || 0 }))
        if (sort === 'score') {
          const sorted = [...normalized].sort((a, b) => {
            const diff = getDisplayScore(b) - getDisplayScore(a)
            if (diff !== 0) return diff
            const ka = `${a.id || 0}-${a.provider}-${a.external_id}`
            const kb = `${b.id || 0}-${b.provider}-${b.external_id}`
            return ka.localeCompare(kb)
          })
          setCandidates(sorted)
        } else {
          setCandidates(normalized)
        }
      })
      .catch(() => {})
  }, [selectedTrack, sort, ytPreferExtended, getDisplayScore, strict])

  React.useEffect(() => { load() }, [load])

  const displayed = React.useMemo(() => {
    // No score limit when strict filter is unchecked
    if (!strict) return candidates
    const filtered = candidates.filter(c => c.chosen || getDisplayScore(c) >= MIN_SCORE)
    return filtered
  }, [candidates, strict, getDisplayScore])

  // Load track duration to compute signed delta
  React.useEffect(() => {
    if (selectedTrack == null) { setTrackDurationMs(null); return }
    let aborted = false
    fetch(`/api/v1/tracks/${selectedTrack}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (!aborted) setTrackDurationMs(data?.duration_ms ?? null) })
      .catch(() => { if (!aborted) setTrackDurationMs(null) })
    return () => { aborted = true }
  }, [selectedTrack])
  const runYouTubeSearch = async () => {
    if (selectedTrack == null) return
    setYtLoading(true)
    setYtStatus('')
    try {
      const params = new URLSearchParams({ prefer_extended: String(ytPreferExtended), persist: String(ytPersist) })
      const r = await fetch(`/api/v1/tracks/${selectedTrack}/youtube/search?` + params.toString())
      if (!r.ok) {
        const msg = await r.text().catch(() => '')
        setYtStatus(`Search failed (${r.status}). ${msg || ''}`)
      } else {
        await r.json().catch(() => null)
        // Refresh candidates after a search; explicit only
        await load()
        // Notify other panels if needed
        window.dispatchEvent(new Event('candidates:changed'))
        setYtStatus(ytPersist ? 'Search saved candidates.' : 'Search completed (not persisted).')
      }
    } catch (e: any) {
      console.error('YouTube search error', e)
      setYtStatus(`Search error: ${e?.message || 'Network error'}`)
    } finally {
      setYtLoading(false)
    }
  }

  const choose = async (id: number) => {
    await fetch(`/api/v1/candidates/${id}/choose`, { method: 'POST' })
    load()
  }

  const downloadChosen = async (candId: number, trackId: number) => {
    // Choose this candidate and then force enqueue a download regardless of duplicates
    await fetch(`/api/v1/candidates/${candId}/choose`, { method: 'POST' })
    await fetch(`/api/v1/downloads/enqueue?track_id=${trackId}&candidate_id=${candId}&force=true`, { method: 'POST' })
    // Let user know; the Downloads page can show progress if needed
    window.dispatchEvent(new Event('downloads:changed'))
    alert('Download enqueued with manual override')
  }

  const addManual = async () => {
    if (selectedTrack == null) return
    const payload = {
      track_id: selectedTrack,
      provider: manual.provider,
      external_id: manual.external_id || manual.url || 'manual',
      url: manual.url,
      title: manual.title,
      duration_sec: manual.duration_sec ? Number(manual.duration_sec) : null,
      score: manual.score ? Number(manual.score) : 0.0
    }
    const r = await fetch('/api/v1/candidates/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    if (r.ok) {
      setManual({ provider: 'youtube', external_id: '', url: '', title: '', duration_sec: '', score: '' })
      load()
    }
  }

  return (
    <section style={{ border: '1px solid #ddd', padding: 16, borderRadius: 8 }}>
      <h2>Search Candidates</h2>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
        <select value={sort} onChange={e => setSort(e.target.value as any)}>
          <option value='score'>Sort: Score</option>
          <option value='duration_delta'>Sort: Duration Δ</option>
        </select>
        <button disabled={selectedTrack == null} onClick={load}>Refresh</button>
        <div style={{ marginLeft: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <button disabled={selectedTrack == null || ytLoading} onClick={runYouTubeSearch}>{ytLoading ? 'Searching…' : 'YouTube Search'}</button>
          {ytStatus && <span style={{ color: '#555' }}>{ytStatus}</span>}
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input type='checkbox' checked={ytPreferExtended} onChange={e => setYtPreferExtended(e.target.checked)} /> Prefer Extended/Club Mix
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <input type='checkbox' checked={ytPersist} onChange={e => setYtPersist(e.target.checked)} /> Persist
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4 }} title='When unchecked, show all candidates (no score limit)'>
            <input type='checkbox' checked={strict} onChange={e => setStrict(e.target.checked)} /> Strict filter (score ≥ 0.50; unchecked = no limit)
          </label>
        </div>
      </div>
      {selectedTrack && (
        <>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left' }}>
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
              {displayed.map(c => {
                const rowKey = getRowKey(c)
                return (
                <React.Fragment key={rowKey}>
                  <tr style={{ background: c.chosen ? '#e6ffe6' : 'transparent' }}>
                    <td>{c.chosen ? '★' : ''}</td>
                    <td>{renderThumbCell(c, expanded, setExpanded, rowKey)}</td>
                    <td style={{ maxWidth: 360 }} title={c.title}>
                      <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.title}</div>
                      {c.score_breakdown && (
                        <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                          {renderBadge('Text', c.score_breakdown.text, c.score_breakdown.details)}
                          {renderBadge('Duration', c.score_breakdown.duration, c.score_breakdown.details)}
                          {renderBadge('Channel', c.score_breakdown.channel, c.score_breakdown.details)}
                          {renderBadge('Extended', c.score_breakdown.extended, c.score_breakdown.details)}
                          {renderBadge('Penalty', c.score_breakdown.penalty, c.score_breakdown.details)}
                        </div>
                      )}
                    </td>
                    <td>{renderSourceCell(c, expanded, setExpanded, rowKey)}</td>
                    <td>{getDisplayScore(c).toFixed(3)}</td>
                    <td>{c.duration_sec != null ? formatHMS(c.duration_sec) : '-'}</td>
                    <td>{renderSignedDelta(trackDurationMs, c.duration_sec, c.duration_delta_sec)}</td>
                    <td>
                      {!c.chosen && c.id > 0 && <button onClick={() => choose(c.id)}>Choose</button>}
                      {c.id > 0 && (
                        <button onClick={() => downloadChosen(c.id, c.track_id)} style={{ marginLeft: 6 }}>Download</button>
                      )}
                    </td>
                  </tr>
                  {expanded.has(rowKey) && c.provider === 'youtube' && (
                    <tr key={`exp-${rowKey}`}>
                      <td colSpan={8}>
                        {renderYouTubeEmbed(c)}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )})}
              {candidates.length === 0 && (
                <tr><td colSpan={8} style={{ textAlign: 'center', padding: 8 }}>No candidates</td></tr>
              )}
            </tbody>
          </table>
          <div style={{ marginTop: 12 }}>
            <h3>Manual Add</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <input placeholder='Title' value={manual.title} onChange={e => setManual(m => ({ ...m, title: e.target.value }))} />
              <input placeholder='URL' value={manual.url} onChange={e => setManual(m => ({ ...m, url: e.target.value }))} />
              <input placeholder='Score' value={manual.score} onChange={e => setManual(m => ({ ...m, score: e.target.value }))} style={{ width: 80 }} />
              <input placeholder='Duration (s)' value={manual.duration_sec} onChange={e => setManual(m => ({ ...m, duration_sec: e.target.value }))} style={{ width: 110 }} />
              <button onClick={addManual}>Add</button>
            </div>
          </div>
        </>
      )}
    </section>
  )
}

// Provide a default export to avoid transient Vite named export resolution issues after refactors
export default CandidatesPanel

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

function renderBadge(label: string, value: number, details?: any) {
  const sign = value > 0 ? '+' : value < 0 ? '-' : ''
  const abs = Math.abs(value)
  const bg = value > 0 ? '#e6ffed' : value < 0 ? '#ffecec' : '#f2f2f2'
  const color = value > 0 ? '#036b26' : value < 0 ? '#a40000' : '#555'
  let title = label
  if (details) {
    const parts: string[] = []
    if (label === 'Extended') {
      if (details.extended_base != null) parts.push(`base=${details.extended_base.toFixed(3)}`)
      if (details.extended_length_bonus) parts.push(`length_bonus=+${details.extended_length_bonus.toFixed(3)}`)
    } else if (label === 'Penalty') {
      if (details.tokens_penalty != null) parts.push(`tokens=${details.tokens_penalty.toFixed(3)}`)
      if (details.keywords_penalty != null) parts.push(`keywords=${details.keywords_penalty.toFixed(3)}`)
    } else if (label === 'Text') {
      if (details.text_similarity != null) parts.push(`similarity=${details.text_similarity.toFixed(3)}`)
    } else if (label === 'Duration') {
      if (details.duration_bonus != null) parts.push(`bonus=${details.duration_bonus.toFixed(3)}`)
    } else if (label === 'Channel') {
      if (details.channel_bonus != null) parts.push(`bonus=${details.channel_bonus.toFixed(3)}`)
    }
    if (parts.length) title = `${label}: ${parts.join(', ')}`
  }
  return (
    <span style={{ background: bg, color, borderRadius: 4, padding: '2px 6px', fontSize: 12 }} title={title}>
      {label}: {sign}{abs.toFixed(3)}
    </span>
  )
}
