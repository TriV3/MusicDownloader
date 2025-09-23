import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import './Header.css'

export const Header: React.FC = () => {
  const location = useLocation()
  
  const isActive = (path: string) => {
    return location.pathname === path
  }

  return (
    <header className="header">
      <div className="header-container">
        <div className="header-brand">
          <Link to="/" className="brand-link">
            <div className="brand-icon">🎵</div>
            <span className="brand-text">Music Downloader</span>
          </Link>
        </div>
        
        <nav className="header-nav">
          <Link 
            to="/" 
            className={`nav-link ${isActive('/') ? 'active' : ''}`}
          >
            Dashboard
          </Link>
          <Link 
            to="/playlists" 
            className={`nav-link ${isActive('/playlists') ? 'active' : ''}`}
          >
            Playlists
          </Link>
          <Link 
            to="/tracks" 
            className={`nav-link ${isActive('/tracks') ? 'active' : ''}`}
          >
            Tracks
          </Link>
          <Link 
            to="/import" 
            className={`nav-link ${isActive('/import') ? 'active' : ''}`}
          >
            Import
          </Link>
          <Link 
            to="/downloads" 
            className={`nav-link ${isActive('/downloads') ? 'active' : ''}`}
          >
            Downloads
          </Link>
        </nav>

        <div className="header-actions">
          <button className="action-btn secondary">
            Settings
          </button>
        </div>
      </div>
    </header>
  )
}

export default Header