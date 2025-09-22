import React from 'react'
import './Footer.css'

export const Footer: React.FC = () => {
  return (
    <footer className="footer">
      <div className="footer-container">
        <div className="footer-content">
          <div className="footer-section">
            <h4>Music Downloader</h4>
            <p>Download and organize your music library</p>
          </div>
          
          <div className="footer-section">
            <h4>Features</h4>
            <ul>
              <li>Spotify Integration</li>
              <li>YouTube Search</li>
              <li>Auto Download</li>
              <li>Library Management</li>
            </ul>
          </div>
          
          <div className="footer-section">
            <h4>Status</h4>
            <div className="status-indicator">
              <span className="status-dot online"></span>
              <span>System Online</span>
            </div>
          </div>
        </div>
        
        <div className="footer-bottom">
          <p>&copy; 2025 Music Downloader. Built with FastAPI & React.</p>
        </div>
      </div>
    </footer>
  )
}

export default Footer