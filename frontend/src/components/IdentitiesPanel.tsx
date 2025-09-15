import React from 'react'
import { useParams } from 'react-router-dom'

export type Track = { id: number; title: string; artists: string }
export type Identity = { id: number; track_id: number; provider: string; provider_track_id: string; provider_url?: string; fingerprint?: string; created_at?: string }

export const IdentitiesPanel: React.FC = () => {
  const { id } = useParams()
  const selectedTrack = id ? Number(id) : null
  const [identities, setIdentities] = React.useState<Identity[]>([])
  const [editing, setEditing] = React.useState<Identity | null>(null)
  const [form, setForm] = React.useState<Partial<Identity>>({})

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
      {selectedTrack && (
        <div style={{ display: 'grid', gap: 6 }}>
          {identities.map(i => (
            <div key={i.id} style={{ padding: 8, border: '1px solid #ccc', borderRadius: 4, background: '#fafafa' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <div>
                  <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{i.provider}</span>
                  <span> • </span>
                  {i.provider_url
                    ? <a href={i.provider_url} target="_blank" rel="noreferrer" title={i.provider_url}>{i.provider_track_id}</a>
                    : <code>{i.provider_track_id}</code>}
                </div>
                <button onClick={() => startEdit(i)}>Edit</button>
              </div>
              <small>
                ID {i.id}
                <span> • </span>
                {i.fingerprint ? 'Fingerprint: present' : 'Fingerprint: none'}
                {i.created_at && <>
                  <span> • </span>
                  <span>{new Date(i.created_at).toLocaleString()}</span>
                </>}
              </small>
            </div>
          ))}
          {identities.length === 0 && (
            <div style={{ padding: 8, border: '1px dashed #ccc', borderRadius: 4, color: '#666' }}>
              No identities for this track.
            </div>
          )}
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

export default IdentitiesPanel
