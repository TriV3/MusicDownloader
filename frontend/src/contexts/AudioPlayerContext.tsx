import React, { createContext, useContext, useState, useCallback } from 'react'

export interface Track {
  id: number
  title: string
  artists: string
  duration_ms?: number | null
}

interface AudioPlayerContextType {
  currentTrack: Track | null
  isPlaying: boolean
  audioUrl: string | null
  playTrack: (track: Track, audioUrl: string) => void
  pauseTrack: () => void
  stopTrack: () => void
  togglePlayPause: () => void
}

const AudioPlayerContext = createContext<AudioPlayerContextType | undefined>(undefined)

export const useAudioPlayer = () => {
  const context = useContext(AudioPlayerContext)
  if (!context) {
    throw new Error('useAudioPlayer must be used within an AudioPlayerProvider')
  }
  return context
}

interface AudioPlayerProviderProps {
  children: React.ReactNode
}

export const AudioPlayerProvider: React.FC<AudioPlayerProviderProps> = ({ children }) => {
  const [currentTrack, setCurrentTrack] = useState<Track | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)

  const playTrack = useCallback((track: Track, url: string) => {
    // If same track, just toggle play/pause
    if (currentTrack?.id === track.id) {
      setIsPlaying(true)
      return
    }

    // New track
    setCurrentTrack(track)
    setAudioUrl(url)
    setIsPlaying(true)
  }, [currentTrack])

  const pauseTrack = useCallback(() => {
    setIsPlaying(false)
  }, [])

  const stopTrack = useCallback(() => {
    setCurrentTrack(null)
    setAudioUrl(null)
    setIsPlaying(false)
  }, [])

  const togglePlayPause = useCallback(() => {
    setIsPlaying(prev => !prev)
  }, [])

  const value: AudioPlayerContextType = {
    currentTrack,
    isPlaying,
    audioUrl,
    playTrack,
    pauseTrack,
    stopTrack,
    togglePlayPause
  }

  return (
    <AudioPlayerContext.Provider value={value}>
      {children}
    </AudioPlayerContext.Provider>
  )
}

export default AudioPlayerProvider