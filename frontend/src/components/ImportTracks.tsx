import React from 'react'

type ImportPreviewItem = {
  artists: string
  title: string
  genre?: string
  bpm?: number
  duration_ms?: number | null
  duplicate?: boolean
}

type DryRunResponse = {
  dry_run: boolean
  received: number
  valid: number
  errors: { index: number; error: string }[]
  to_create_non_duplicates: number
  created: number
  items: ImportPreviewItem[] | null
}

export const ImportTracks: React.FC = () => {
  const [file, setFile] = React.useState<File | null>(null)
  const [dragActive, setDragActive] = React.useState(false)
  const [loading, setLoading] = React.useState(false)
  const [preview, setPreview] = React.useState<DryRunResponse | null>(null)
  const [confirmedResult, setConfirmedResult] = React.useState<DryRunResponse | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const onFiles = (fList: FileList | null) => {
    if (fList && fList.length > 0) {
      setFile(fList[0])
      setPreview(null)
      setConfirmedResult(null)
      setError(null)
    }
  }

  const runDryRun = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('dry_run', 'true')
      const resp = await fetch('/api/v1/tracks/import/json', { method: 'POST', body: fd })
      if (!resp.ok) {
        const text = await resp.text()
        throw new Error('Dry-run failed: ' + text.slice(0, 400))
      }
      const data: DryRunResponse = await resp.json()
      setPreview(data)
    } catch (e: any) {
      setError(e.message + '\nCheck required keys: artists,title,genre,bpm (legacy French keys are auto-mapped).')
    } finally {
      setLoading(false)
    }
  }

  const confirmImport = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('dry_run', 'false')
      const resp = await fetch('/api/v1/tracks/import/json', { method: 'POST', body: fd })
      if (!resp.ok) {
        const text = await resp.text()
        throw new Error('Import failed: ' + text.slice(0, 400))
      }
      const data: DryRunResponse = await resp.json()
      setConfirmedResult(data)
    } catch (e: any) {
      setError(e.message + '\nVerify the file is the same one used for a successful dry run.')
    } finally {
      setLoading(false)
    }
  }

  const dropHandlers = {
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); setDragActive(true) },
    onDragLeave: (e: React.DragEvent) => { e.preventDefault(); setDragActive(false) },
    onDrop: (e: React.DragEvent) => { e.preventDefault(); setDragActive(false); onFiles(e.dataTransfer.files) }
  }

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <h2>Import Tracks (JSON)</h2>
      <p style={{ maxWidth: 760 }}>
        Provide a JSON array of objects with required fields: <code>artists, title, genre, bpm</code> and optional <code>duration</code> (mm:ss).
        Use Dry Run first to preview duplicates and validation errors before Confirm Import.
      </p>
      <div
        {...dropHandlers}
        style={{
          border: '2px dashed ' + (dragActive ? '#2d6cdf' : '#888'),
          padding: 32,
          textAlign: 'center',
          borderRadius: 12,
          background: dragActive ? '#f0f7ff' : '#fafafa',
          position: 'relative'
        }}
      >
        <p style={{ margin: 0 }}>
          {file ? <><strong>{file.name}</strong> ({Math.round(file.size / 1024)} KB)</> : 'Drag & drop JSON file here or click to select'}
        </p>
        <input
          type="file"
          accept="application/json"
          style={{
            opacity: 0,
            position: 'absolute',
            inset: 0,
            cursor: 'pointer',
            width: '100%',
            height: '100%'
          }}
          onChange={e => onFiles(e.target.files)}
        />
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <button disabled={!file || loading} onClick={runDryRun}>Dry Run</button>
        <button disabled={!file || loading || !preview} onClick={confirmImport}>Confirm Import</button>
        {loading && <span>Processing...</span>}
      </div>
      {error && <div style={{ color: 'red' }}>{error}</div>}
      {preview && (
        <div style={{ border: '1px solid #ddd', padding: 12, borderRadius: 8 }}>
          <h3 style={{ marginTop: 0 }}>Dry Run Result</h3>
          <p>
            Received: {preview.received} | Valid: {preview.valid} | Non-duplicates to create: {preview.to_create_non_duplicates} | Errors: {preview.errors.length}
          </p>
          {preview.errors.length > 0 && (
            <details>
              <summary>Errors ({preview.errors.length})</summary>
              <ul>
                {preview.errors.map(er => <li key={er.index}>Row {er.index + 1}: {er.error}</li>)}
              </ul>
            </details>
          )}
          {preview.items && preview.items.length > 0 && (
            <div style={{ maxHeight: 260, overflow: 'auto', border: '1px solid #eee' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
                <thead>
                  <tr>
                    <th style={th}>Artists</th>
                    <th style={th}>Title</th>
                    <th style={th}>Genre</th>
                    <th style={th}>BPM</th>
                    <th style={th}>Duration (ms)</th>
                    <th style={th}>Duplicate</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.items.map((it, i) => (
                    <tr key={i} style={{ background: it.duplicate ? '#ffecec' : i % 2 ? '#fafafa' : 'white' }}>
                      <td style={td}>{it.artists}</td>
                      <td style={td}>{it.title}</td>
                      <td style={td}>{it.genre}</td>
                      <td style={td}>{it.bpm}</td>
                      <td style={td}>{it.duration_ms ?? ''}</td>
                      <td style={td}>{it.duplicate ? 'Yes' : 'No'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
      {confirmedResult && (
        <div style={{ border: '1px solid #cce5cc', padding: 12, borderRadius: 8, background: '#f6fff6' }}>
          <strong>Import Complete:</strong> Created {confirmedResult.created} new tracks. (Attempted {confirmedResult.received})
        </div>
      )}
    </section>
  )
}

const th: React.CSSProperties = { textAlign: 'left', borderBottom: '1px solid #ccc', padding: '4px 6px', position: 'sticky', top: 0, background: '#f7f7f7' }
const td: React.CSSProperties = { padding: '4px 6px', borderBottom: '1px solid #eee', verticalAlign: 'top' }
