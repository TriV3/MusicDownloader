import React from 'react'
import { NormalizationPlayground } from './components/NormalizationPlayground'
import { IdentitiesPanel } from './components/IdentitiesPanel'
import { CandidatesPanel } from './components/CandidatesPanel'
import { TrackManager } from './components/TrackManager'

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
      <TrackManager />
      <NormalizationPlayground />
      <IdentitiesPanel />
      <CandidatesPanel />
    </main>
  )
}
