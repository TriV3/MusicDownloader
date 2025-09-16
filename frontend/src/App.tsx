import React from 'react'
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import DashboardPage from './routes/DashboardPage'
import TracksPage from './routes/TracksPage'
import ImportPage from './routes/ImportPage'
import ToolsPage from './routes/ToolsPage'
import TrackDetailPage, { TrackOverviewTab, TrackIdentitiesTab, TrackCandidatesTab } from './routes/TrackDetailPage'
import DownloadsPage from './routes/DownloadsPage'

export default function App() {
  return (
    <BrowserRouter>
      <main style={{ fontFamily: 'system-ui, sans-serif', padding: 24, display: 'grid', gap: 16 }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 12 }}>
          <h1 style={{ margin: 0 }}>Music Downloader</h1>
          <nav style={{ display: 'flex', gap: 8 }}>
            <NavLink to="/" end>Dashboard</NavLink>
            <NavLink to="/tracks">Tracks</NavLink>
            <NavLink to="/import">Import</NavLink>
            <NavLink to="/tools">Tools</NavLink>
            <NavLink to="/downloads">Downloads</NavLink>
          </nav>
        </header>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/tracks" element={<TracksPage />} />
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
      </main>
    </BrowserRouter>
  )
}
