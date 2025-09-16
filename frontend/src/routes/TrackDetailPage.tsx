import React from 'react'
import { useParams, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { IdentitiesPanel } from '../components/IdentitiesPanel'
import { CandidatesPanel } from '../components/CandidatesPanel'

export const TrackDetailPage: React.FC = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const tid = Number(id)

  React.useEffect(() => {
    if (!id) navigate('/tracks')
  }, [id, navigate])

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <h2>Track #{id}</h2>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <NavLink to="overview">Overview</NavLink>
        <NavLink to="identities">Identities</NavLink>
  <NavLink to="candidates">Candidates</NavLink>
      </div>
      <div>
        <Outlet />
      </div>
    </div>
  )
}

export const TrackOverviewTab: React.FC = () => {
  const { id } = useParams()
  const [track, setTrack] = React.useState<any>(null)
  React.useEffect(() => {
    if (!id) return
    fetch(`/api/v1/tracks/${id}`)
      .then(r => r.json())
      .then(setTrack)
      .catch(() => setTrack(null))
  }, [id])
  if (!track) return <div>Loading...</div>
  return (
    <div style={{ display: 'grid', gap: 4 }}>
      <div><b>Artists:</b> {track.artists}</div>
      <div><b>Title:</b> {track.title}</div>
      <div><b>Normalized:</b> {track.normalized_artists} — {track.normalized_title}</div>
      {track.duration_ms != null && <div><b>Duration:</b> {(track.duration_ms/1000).toFixed(0)} s</div>}
    </div>
  )
}

export const TrackIdentitiesTab: React.FC = () => <IdentitiesPanel />
export const TrackCandidatesTab: React.FC = () => <CandidatesPanel />

export default TrackDetailPage
