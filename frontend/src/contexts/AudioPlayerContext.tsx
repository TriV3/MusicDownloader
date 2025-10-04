import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react'

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
  audioElement: HTMLAudioElement | null
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
  // Keep a single shared Audio element so we can force-stop and auto-play when switching
  const audioRef = useRef<HTMLAudioElement | null>(null)
  if (!audioRef.current && typeof Audio !== 'undefined') {
    audioRef.current = new Audio()
    audioRef.current.preload = 'metadata'
  }

  const playTrack = useCallback((track: Track, url: string) => {
    const audio = audioRef.current
    if (!audio) {
      // Fallback: just set state; GlobalAudioPlayer will render <audio>
      setCurrentTrack(track)
      setAudioUrl(url)
      setIsPlaying(true)
      return
    }
    // Same track: if paused -> play
    if (currentTrack?.id === track.id) {
      setIsPlaying(true)
      audio.play().catch(() => {})
      return
    }
    // Switching track: pause & reset previous
    audio.pause()
    audio.currentTime = 0
    // Update state first
    setCurrentTrack(track)
    setAudioUrl(url)
    setIsPlaying(true)
    // Assign new src then play
    audio.src = url
    audio.play().catch(() => {})
  }, [currentTrack])

  const pauseTrack = useCallback(() => {
    setIsPlaying(false)
    audioRef.current?.pause()
  }, [])

  const stopTrack = useCallback(() => {
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.currentTime = 0
      audio.removeAttribute('src')
      audio.load()
    }
    setCurrentTrack(null)
    setAudioUrl(null)
    setIsPlaying(false)
  }, [])

  const togglePlayPause = useCallback(() => {
    setIsPlaying(prev => {
      const next = !prev
      const audio = audioRef.current
      if (audio) {
        if (next) {
          audio.play().catch(() => {})
        } else {
          audio.pause()
        }
      }
      return next
    })
  }, [])

  // Sync external state changes to underlying audio element if url changes (e.g., first load without direct play invocation)
  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !audioUrl) return
    if (audio.src !== audioUrl) {
      audio.src = audioUrl
      if (isPlaying) {
        audio.play().catch(() => {})
      }
    }
  }, [audioUrl, isPlaying])

  // Expose basic ended handler to maintain isPlaying flag if audio finished
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const handleEnded = () => {
      setIsPlaying(false)
    }
    audio.addEventListener('ended', handleEnded)
    return () => {
      audio.removeEventListener('ended', handleEnded)
    }
  }, [])

  const value: AudioPlayerContextType = {
    currentTrack,
    isPlaying,
    audioUrl,
    playTrack,
    pauseTrack,
    stopTrack,
    togglePlayPause,
    audioElement: audioRef.current
  }

  return (
    <AudioPlayerContext.Provider value={value}>
      {children}
    </AudioPlayerContext.Provider>
  )
}

export default AudioPlayerProvider