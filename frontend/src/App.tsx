import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout/Layout'
import DashboardPage from './routes/DashboardPage'
import TracksPage from './routes/TracksPage'
import PlaylistsPage from './routes/PlaylistsPage'
import OAuthSpotifyCallback from './routes/OAuthSpotifyCallback'
import ImportPage from './routes/ImportPage'
import ToolsPage from './routes/ToolsPage'
import TrackDetailPage, { TrackOverviewTab, TrackIdentitiesTab, TrackCandidatesTab } from './routes/TrackDetailPage'
import DownloadsPage from './routes/DownloadsPage'
import './styles/globals.css'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/tracks" element={<TracksPage />} />
          <Route path="/playlists" element={<PlaylistsPage />} />
          <Route path="/oauth/spotify/callback" element={<OAuthSpotifyCallback />} />
          <Route path="/tracks/:id" element={<TrackDetailPage />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<TrackOverviewTab />} />
            <Route path="identities" element={<TrackIdentitiesTab />} />
            <Route path="candidates" element={<TrackCandidatesTab />} />
          </Route>
          <Route path="/import" element={<ImportPage />} />
          <Route path="/tools" element={<ToolsPage />} />
          <Route path="/downloads" element={<DownloadsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
