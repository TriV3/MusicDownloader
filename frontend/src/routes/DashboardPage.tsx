import React from 'react'

export const DashboardPage: React.FC = () => {
  const [status, setStatus] = React.useState<string>('...')
  React.useEffect(() => {
    fetch('/api/v1/health')
      .then(r => r.json())
      .then(d => setStatus(d.status))
      .catch(() => setStatus('error'))
  }, [])
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <h2 style={{ marginTop: 0 }}>Dashboard</h2>
      <p>API health: {status}</p>
      <div style={{ opacity: 0.7 }}>Quick stats and recent activity will appear here.</div>
    </div>
  )
}

export default DashboardPage
