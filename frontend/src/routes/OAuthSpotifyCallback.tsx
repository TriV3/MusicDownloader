import React from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

const OAuthSpotifyCallback: React.FC = () => {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [status, setStatus] = React.useState('Processing…')

  React.useEffect(() => {
    const code = params.get('code')
    const state = params.get('state')
    if (!code || !state) {
      setStatus('Missing code/state in callback URL')
      return
    }
    ;(async () => {
      try {
        const r = await fetch(`/api/v1/oauth/spotify/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`)
        if (!r.ok) {
          const t = await r.text()
          throw new Error(t)
        }
        setStatus('Authorized. Redirecting…')
        setTimeout(() => navigate('/playlists', { replace: true }), 500)
      } catch (e: any) {
        setStatus(`Authorization failed: ${e?.message || 'error'}`)
      }
    })()
  }, [navigate, params])

  return (
    <div>
      <h2>Spotify Authorization</h2>
      <p>{status}</p>
    </div>
  )
}

export default OAuthSpotifyCallback
