import React from 'react'
import { NormalizationPlayground } from './components/NormalizationPlayground'
import { IdentitiesPanel } from './components/IdentitiesPanel'
import { CandidatesPanel } from './components/CandidatesPanel'
import { TrackManager } from './components/TrackManager'
import { ImportTracks } from './components/ImportTracks'

export default function App() {
  const [status, setStatus] = React.useState<string>('...')

  React.useEffect(() => {
    fetch('/api/v1/health')
      .then(r => r.json())
      .then(d => setStatus(d.status))
      .catch(() => setStatus('error'))
  }, [])

  const [tab, setTab] = React.useState<'home' | 'import'>('home')
  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: 24, display: 'grid', gap: 16 }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 12 }}>
        <h1 style={{ margin: 0 }}>Music Downloader</h1>
        <nav style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => setTab('home')} disabled={tab==='home'}>Home</button>
          <button onClick={() => setTab('import')} disabled={tab==='import'}>Import</button>
        </nav>
      </header>
      <p style={{ marginTop: 0 }}>API health: {status}</p>
      {tab === 'import' ? (
        <ImportTracks />
      ) : (
        <div style={{ display: 'grid', gap: 16 }}>
          <TrackManager />
          <NormalizationPlayground />
          <IdentitiesPanel />
          <CandidatesPanel />
        </div>
      )}
    </main>
  )
}
