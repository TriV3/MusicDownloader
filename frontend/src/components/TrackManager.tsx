import React from 'react'
import { Link } from 'react-router-dom'
import type { NormalizationPreview } from './NormalizationPlayground'

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
  const [tracks, setTracks] = React.useState<TrackRead[]>([])
  const [rawArtists, setRawArtists] = React.useState('')
  const [rawTitle, setRawTitle] = React.useState('')
  const [preview, setPreview] = React.useState<NormalizationPreview | null>(null)
  const [loading, setLoading] = React.useState(false)

  const loadTracks = React.useCallback(() => {
    fetch('/api/v1/tracks/')
      .then(r => r.json())
      .then(d => setTracks(d))
      .catch(() => {})
  }, [])

  React.useEffect(() => { loadTracks() }, [loadTracks])

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

  return (
    <section style={{ border: '1px solid #ddd', padding: 16, borderRadius: 8 }}>
      <h2>Track Manager</h2>
      <div style={{ display: 'flex', gap: 12, marginBottom: 8 }}>
        <input placeholder='Artists' value={rawArtists} onChange={e => setRawArtists(e.target.value)} style={{ flex: 1 }} />
        <input placeholder='Title' value={rawTitle} onChange={e => setRawTitle(e.target.value)} style={{ flex: 1 }} />
        <button disabled={!rawArtists || !rawTitle || loading} onClick={create}>Create</button>
      </div>
      {preview && (
        <div style={{ marginBottom: 12, fontSize: 13, fontFamily: 'ui-monospace, monospace', background: '#f7f7f7', padding: 8, borderRadius: 4 }}>
          <strong>Preview:</strong> {preview.normalized_artists} – {preview.normalized_title}
        </div>
      )}
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ textAlign: 'left' }}>
            <th>ID</th>
            <th>Cover</th>
            <th>Artists</th>
            <th>Title</th>
            <th>Genre</th>
            <th>BPM</th>
            <th>Duration</th>
            <th>Created</th>
            <th>Updated</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {tracks.map(t => (
            <tr key={t.id}>
              <td>{t.id}</td>
              <td>
                {t.cover_url ? (
                  <img src={t.cover_url} alt="cover" style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 4 }} />
                ) : (
                  <div style={{ width: 48, height: 48, background: '#eee', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999', fontSize: 10 }}>No image</div>
                )}
              </td>
              <td>{t.artists}</td>
              <td>{t.title}</td>
              <td>{t.genre ?? '-'}</td>
              <td>{t.bpm ?? '-'}</td>
              <td>{t.duration_ms != null ? formatDuration(t.duration_ms) : '-'}</td>
              <td>{formatDate(t.created_at)}</td>
              <td>{formatDate(t.updated_at)}</td>
              <td style={{ display: 'flex', gap: 8 }}>
                <Link to={`/tracks/${t.id}`}>View</Link>
                <button onClick={() => remove(t.id)}>Delete</button>
              </td>
            </tr>
          ))}
          {tracks.length === 0 && <tr><td colSpan={10} style={{ textAlign: 'center', padding: 8 }}>No tracks</td></tr>}
        </tbody>
      </table>
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
