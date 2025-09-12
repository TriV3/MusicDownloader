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
    </main>
  )
}
