import React from 'react'

type Preview = {
  primary_artist: string
  clean_artists: string
  clean_title: string
  normalized_artists: string
  normalized_title: string
  is_remix_or_edit: boolean
  is_live: boolean
  is_remaster: boolean
}

function NormalizationPlayground() {
  const [artists, setArtists] = React.useState('')
  const [title, setTitle] = React.useState('')
  const [preview, setPreview] = React.useState<Preview | null>(null)

  React.useEffect(() => {
    const ctrl = new AbortController()
    const run = async () => {
      const params = new URLSearchParams({ artists, title })
      const r = await fetch(`/api/v1/tracks/normalize/preview?${params.toString()}`, { signal: ctrl.signal })
      if (!r.ok) return
      const data = await r.json()
      setPreview(data)
    }
    // debounce a bit
    const id = setTimeout(() => { run().catch(() => {}) }, 120)
    return () => { clearTimeout(id); ctrl.abort() }
  }, [artists, title])

  return (
    <section style={{ border: '1px solid #ddd', padding: 16, borderRadius: 8 }}>
      <h2>Normalization Playground</h2>
      <div style={{ display: 'flex', gap: 12 }}>
        <label style={{ flex: 1 }}>
          <div>Artists</div>
          <input value={artists} onChange={e => setArtists(e.target.value)} style={{ width: '100%' }} />
        </label>
        <label style={{ flex: 1 }}>
          <div>Title</div>
          <input value={title} onChange={e => setTitle(e.target.value)} style={{ width: '100%' }} />
        </label>
      </div>
      {preview && (
        <div style={{ marginTop: 12, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
          <div><strong>Primary artist:</strong> {preview.primary_artist}</div>
          <div><strong>Clean artists:</strong> {preview.clean_artists}</div>
          <div><strong>Clean title:</strong> {preview.clean_title}</div>
          <div><strong>Normalized artists:</strong> {preview.normalized_artists}</div>
          <div><strong>Normalized title:</strong> {preview.normalized_title}</div>
          <div><strong>Flags:</strong> remix/edit={String(preview.is_remix_or_edit)} • live={String(preview.is_live)} • remaster={String(preview.is_remaster)}</div>
        </div>
      )}
    </section>
  )
}

type Track = { id: number; title: string; artists: string }
type Identity = { id: number; track_id: number; provider: string; provider_track_id: string; provider_url?: string; fingerprint?: string; created_at?: string }

function IdentitiesPanel() {
  const [tracks, setTracks] = React.useState<Track[]>([])
  const [selectedTrack, setSelectedTrack] = React.useState<number | null>(null)
  const [identities, setIdentities] = React.useState<Identity[]>([])
  const [editing, setEditing] = React.useState<Identity | null>(null)
  const [form, setForm] = React.useState<Partial<Identity>>({})

  React.useEffect(() => {
    fetch('/api/v1/tracks/')
      .then(r => r.json())
      .then(d => setTracks(d))
      .catch(() => {})
  }, [])

  React.useEffect(() => {
    if (selectedTrack == null) { setIdentities([]); return }
    const params = new URLSearchParams({ track_id: String(selectedTrack) })
    fetch('/api/v1/identities/?' + params.toString())
      .then(r => r.json())
      .then(d => setIdentities(d))
      .catch(() => {})
  }, [selectedTrack])

  const startEdit = (ident: Identity) => {
    setEditing(ident)
    setForm(ident)
  }

  const save = async () => {
    if (!editing) return
    const payload = {
      track_id: editing.track_id,
      provider: form.provider || editing.provider,
      provider_track_id: form.provider_track_id || editing.provider_track_id,
      provider_url: form.provider_url || '',
      fingerprint: form.fingerprint || null
    }
    const r = await fetch(`/api/v1/identities/${editing.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    if (r.ok) {
      const updated = await r.json()
      setIdentities(ids => ids.map(i => i.id === updated.id ? updated : i))
      setEditing(null)
    }
  }

  return (
    <section style={{ border: '1px solid #ddd', padding: 16, borderRadius: 8 }}>
      <h2>Track Identities</h2>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <select value={selectedTrack ?? ''} onChange={e => setSelectedTrack(e.target.value ? Number(e.target.value) : null)}>
          <option value=''>-- Select Track --</option>
          {tracks.map(t => <option key={t.id} value={t.id}>{t.id}: {t.artists} - {t.title}</option>)}
        </select>
      </div>
      {selectedTrack && (
        <div style={{ display: 'grid', gap: 6 }}>
          {identities.map(i => (
            <div key={i.id} style={{ padding: 8, border: '1px solid #ccc', borderRadius: 4, background: '#fafafa' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong>{i.provider}:{i.provider_track_id}</strong>
                <button onClick={() => startEdit(i)}>Edit</button>
              </div>
              <small>ID {i.id} • {i.fingerprint ? 'fingerprinted' : 'no fingerprint'}</small>
            </div>
          ))}
        </div>
      )}
      {editing && (
        <div style={{ marginTop: 12, borderTop: '1px solid #eee', paddingTop: 12 }}>
          <h3>Edit Identity #{editing.id}</h3>
            <label style={{ display: 'block', marginBottom: 4 }}>Provider Track ID
              <input value={form.provider_track_id || ''} onChange={e => setForm(f => ({ ...f, provider_track_id: e.target.value }))} />
            </label>
            <label style={{ display: 'block', marginBottom: 4 }}>Provider URL
              <input value={form.provider_url || ''} onChange={e => setForm(f => ({ ...f, provider_url: e.target.value }))} />
            </label>
            <label style={{ display: 'block', marginBottom: 4 }}>Fingerprint
              <input value={form.fingerprint || ''} onChange={e => setForm(f => ({ ...f, fingerprint: e.target.value }))} />
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={save}>Save</button>
              <button onClick={() => setEditing(null)}>Cancel</button>
            </div>
        </div>
      )}
    </section>
  )
}

export default function App() {
  const [status, setStatus] = React.useState<string>('...')

  React.useEffect(() => {
    fetch('/api/v1/health')
      .then(r => r.json())
      .then(d => setStatus(d.status))
      .catch(() => setStatus('error'))
  }, [])

  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: 24, display: 'grid', gap: 16 }}>
      <h1>Music Downloader</h1>
      <p>API health: {status}</p>
      <NormalizationPlayground />
      <IdentitiesPanel />
    </main>
  )
}
