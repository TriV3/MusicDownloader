import React from 'react'
import { TrackManager } from '../components/TrackManager'
import '../styles/tracks.css'

export const TracksPage: React.FC = () => {
  return (
    <div className="tracks-page">
      <div className="tracks-header">
        <h2 className="tracks-title">Tracks</h2>
      </div>
      <TrackManager />
    </div>
  )
}

export default TracksPage
