import React, { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import './Header.css'

export const Header: React.FC = () => {
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  
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
    const handleClickOutside = (event: MouseEvent | TouchEvent) => {
      const target = event.target as Node
      if (
        menuRef.current && 
        !menuRef.current.contains(target) &&
        buttonRef.current &&
        !buttonRef.current.contains(target)
      ) {
        closeMobileMenu()
      }
    }

    if (mobileMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside as EventListener)
      document.addEventListener('touchstart', handleClickOutside as EventListener)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside as EventListener)
      document.removeEventListener('touchstart', handleClickOutside as EventListener)
    }
  }, [mobileMenuOpen])

  useEffect(() => {
    closeMobileMenu()
  }, [location.pathname])

  return (
    <header className="header">
      <div className="header-container">
        <div className="header-brand">
          <Link to="/" className="brand-link">
            <div className="brand-icon">🎵</div>
            <span className="brand-text">Music Downloader</span>
          </Link>
        </div>
        
        <nav ref={menuRef} className={`header-nav ${mobileMenuOpen ? 'mobile-menu-open' : ''}`}>
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
            ref={buttonRef}
            className="mobile-menu-btn" 
            onClick={toggleMobileMenu}
            aria-label="Toggle menu"
            aria-expanded={mobileMenuOpen}
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