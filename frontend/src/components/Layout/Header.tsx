import React, { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import './Header.css'

export const Header: React.FC = () => {
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  
  const isActive = (path: string) => {
    return location.pathname === path
  }

  const toggleMobileMenu = () => {
    setMobileMenuOpen(!mobileMenuOpen)
  }

  const closeMobileMenu = () => {
    setMobileMenuOpen(false)
  }

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        closeMobileMenu()
      }
    }

    if (mobileMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [mobileMenuOpen])

  useEffect(() => {
    closeMobileMenu()
  }, [location.pathname])

  return (
    <header className="header" ref={menuRef}>
      <div className="header-container">
        <div className="header-brand">
          <Link to="/" className="brand-link">
            <div className="brand-icon">🎵</div>
            <span className="brand-text">Music Downloader</span>
          </Link>
        </div>
        
        <nav className={`header-nav ${mobileMenuOpen ? 'mobile-menu-open' : ''}`}>
          <Link 
            to="/" 
            className={`nav-link ${isActive('/') ? 'active' : ''}`}
            onClick={closeMobileMenu}
          >
            Dashboard
          </Link>
          <Link 
            to="/playlists" 
            className={`nav-link ${isActive('/playlists') ? 'active' : ''}`}
            onClick={closeMobileMenu}
          >
            Playlists
          </Link>
          <Link 
            to="/tracks" 
            className={`nav-link ${isActive('/tracks') ? 'active' : ''}`}
            onClick={closeMobileMenu}
          >
            Tracks
          </Link>
          <Link 
            to="/import" 
            className={`nav-link ${isActive('/import') ? 'active' : ''}`}
            onClick={closeMobileMenu}
          >
            Import
          </Link>
          <Link 
            to="/downloads" 
            className={`nav-link ${isActive('/downloads') ? 'active' : ''}`}
            onClick={closeMobileMenu}
          >
            Downloads
          </Link>
        </nav>

        <div className="header-actions">
          <button className="action-btn secondary desktop-only">
            Settings
          </button>
          <button 
            className="mobile-menu-btn" 
            onClick={toggleMobileMenu}
            aria-label="Toggle menu"
            aria-expanded={mobileMenuOpen ? 'true' : 'false'}
          >
            <span className={`hamburger ${mobileMenuOpen ? 'open' : ''}`}>
              <span></span>
              <span></span>
              <span></span>
            </span>
          </button>
        </div>
      </div>
    </header>
  )
}

export default Header