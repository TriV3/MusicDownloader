import React from 'react'

export default function App() {
  const [status, setStatus] = React.useState<string>('...')

  React.useEffect(() => {
    fetch('/api/v1/health')
      .then(r => r.json())
      .then(d => setStatus(d.status))
      .catch(() => setStatus('error'))
  }, [])

  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: 24 }}>
      <h1>Music Downloader</h1>
      <p>API health: {status}</p>
    </main>
  )
}
