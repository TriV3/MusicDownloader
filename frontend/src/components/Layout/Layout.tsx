import React from 'react'
import Header from './Header'
import Footer from './Footer'
import './Layout.css'

type Props = {
  children: React.ReactNode
}

export const Layout: React.FC<Props> = ({ children }) => {
  return (
    <div className="app-layout">
      <Header />
      <main className="main-content">
        <div className="content-container">
          {children}
        </div>
      </main>
      <Footer />
    </div>
  )
}

export default Layout