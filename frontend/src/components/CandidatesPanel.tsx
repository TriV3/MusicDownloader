import React from 'react'
import type { Track } from './IdentitiesPanel'

export type Candidate = { id: number; track_id: number; provider: string; external_id: string; url: string; title: string; score: number; duration_sec?: number; duration_delta_sec?: number; chosen: boolean }

export const CandidatesPanel: React.FC = () => {
  const [tracks, setTracks] = React.useState<Track[]>([])
  const [selectedTrack, setSelectedTrack] = React.useState<number | null>(null)
  const [candidates, setCandidates] = React.useState<Candidate[]>([])
  const [sort, setSort] = React.useState<'score' | 'duration_delta'>('score')
  const [manual, setManual] = React.useState({ provider: 'youtube', external_id: '', url: '', title: '', duration_sec: '', score: '' })

  React.useEffect(() => {
    const loadTracks = () => {
      fetch('/api/v1/tracks/')
        .then(r => r.json())
        .then(d => setTracks(d))
        .catch(() => {})
    }
    loadTracks()
    const handler = () => loadTracks()
    window.addEventListener('tracks:changed', handler)
    return () => window.removeEventListener('tracks:changed', handler)
  }, [])

  const load = React.useCallback(() => {
    if (selectedTrack == null) { setCandidates([]); return }
    const params = new URLSearchParams({ track_id: String(selectedTrack), sort })
    fetch('/api/v1/candidates/?' + params.toString())
      .then(r => r.json())
      .then(d => setCandidates(d))
      .catch(() => {})
  }, [selectedTrack, sort])

  React.useEffect(() => { load() }, [load])

  const choose = async (id: number) => {
    await fetch(`/api/v1/candidates/${id}/choose`, { method: 'POST' })
    load()
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
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <select value={selectedTrack ?? ''} onChange={e => setSelectedTrack(e.target.value ? Number(e.target.value) : null)}>
          <option value=''>-- Select Track --</option>
          {tracks.map(t => <option key={t.id} value={t.id}>{t.id}: {t.artists} - {t.title}</option>)}
        </select>
        <select value={sort} onChange={e => setSort(e.target.value as any)}>
          <option value='score'>Sort: Score</option>
          <option value='duration_delta'>Sort: Duration Δ</option>
        </select>
        <button disabled={selectedTrack == null} onClick={load}>Refresh</button>
      </div>
      {selectedTrack && (
        <>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left' }}>
                <th>Chosen</th>
                <th>Title</th>
                <th>Score</th>
                <th>Dur (s)</th>
                <th>Δ (s)</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map(c => (
                <tr key={c.id} style={{ background: c.chosen ? '#e6ffe6' : 'transparent' }}>
                  <td>{c.chosen ? '★' : ''}</td>
                  <td style={{ maxWidth: 260, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={c.title}>{c.title}</td>
                  <td>{c.score.toFixed(3)}</td>
                  <td>{c.duration_sec ?? '-'}</td>
                  <td>{c.duration_delta_sec != null ? c.duration_delta_sec.toFixed(2) : '-'}</td>
                  <td>
                    {!c.chosen && <button onClick={() => choose(c.id)}>Choose</button>}
                  </td>
                </tr>
              ))}
              {candidates.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: 'center', padding: 8 }}>No candidates</td></tr>
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
