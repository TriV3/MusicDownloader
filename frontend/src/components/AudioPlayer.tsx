import React, { useRef, useEffect, useState, useCallback } from 'react'
import './AudioPlayer.css'

export interface Track {
  id: number
  title: string
  artists: string
  duration_ms?: number | null
}

interface AudioPlayerProps {
  track: Track
  audioUrl: string
  isPlaying: boolean
  onPlay: () => void
  onPause: () => void
  onEnded: () => void
  onClose: () => void
}

export const AudioPlayer: React.FC<AudioPlayerProps> = ({
  track,
  audioUrl,
  isPlaying,
  onPlay,
  onPause,
  onEnded,
  onClose
}) => {
  const audioRef = useRef<HTMLAudioElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const progressRef = useRef<HTMLDivElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [audioBuffer, setAudioBuffer] = useState<AudioBuffer | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const animationFrameRef = useRef<number>()

  // Load and decode audio for waveform
  useEffect(() => {
    const loadAudioBuffer = async () => {
      if (!audioUrl) return
      
      setIsLoading(true)
      try {
        const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
        const response = await fetch(audioUrl)
        const arrayBuffer = await response.arrayBuffer()
        const buffer = await audioContext.decodeAudioData(arrayBuffer)
        setAudioBuffer(buffer)
      } catch (error) {
        console.error('Error loading audio buffer:', error)
      } finally {
        setIsLoading(false)
      }
    }

    loadAudioBuffer()
  }, [audioUrl])

  // Draw waveform
  const drawWaveform = useCallback(() => {
    const canvas = canvasRef.current
    const audio = audioRef.current
    if (!canvas || !audioBuffer || !audio) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const { width, height } = canvas
    ctx.clearRect(0, 0, width, height)

    // Get audio data from first channel
    const data = audioBuffer.getChannelData(0)
    const step = Math.ceil(data.length / width)
    const amp = height / 2

    // Draw waveform background
    ctx.fillStyle = 'rgba(156, 163, 175, 0.3)'
    ctx.beginPath()
    for (let i = 0; i < width; i++) {
      let min = 1.0
      let max = -1.0
      for (let j = 0; j < step; j++) {
        const datum = data[(i * step) + j]
        if (datum < min) min = datum
        if (datum > max) max = datum
      }
      const yMin = (1 + min) * amp
      const yMax = (1 + max) * amp
      ctx.rect(i, yMin, 1, yMax - yMin)
    }
    ctx.fill()

    // Draw progress
    const progress = audio.duration ? audio.currentTime / audio.duration : 0
    const progressWidth = width * progress

    ctx.fillStyle = 'rgba(59, 130, 246, 0.8)'
    ctx.beginPath()
    for (let i = 0; i < progressWidth; i++) {
      let min = 1.0
      let max = -1.0
      for (let j = 0; j < step; j++) {
        const datum = data[(i * step) + j]
        if (datum < min) min = datum
        if (datum > max) max = datum
      }
      const yMin = (1 + min) * amp
      const yMax = (1 + max) * amp
      ctx.rect(i, yMin, 1, yMax - yMin)
    }
    ctx.fill()
  }, [audioBuffer])

  // Animation loop for waveform updates
  useEffect(() => {
    const animate = () => {
      if (isPlaying) {
        drawWaveform()
        animationFrameRef.current = requestAnimationFrame(animate)
      }
    }

    if (isPlaying) {
      animate()
    } else {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
      drawWaveform() // Draw static waveform when paused
    }

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
    }
  }, [isPlaying, drawWaveform])

  // Audio event handlers
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const handleTimeUpdate = () => setCurrentTime(audio.currentTime)
    const handleLoadedMetadata = () => setDuration(audio.duration)
    const handleEnded = () => {
      onEnded()
      setCurrentTime(0)
    }

    audio.addEventListener('timeupdate', handleTimeUpdate)
    audio.addEventListener('loadedmetadata', handleLoadedMetadata)
    audio.addEventListener('ended', handleEnded)

    return () => {
      audio.removeEventListener('timeupdate', handleTimeUpdate)
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata)
      audio.removeEventListener('ended', handleEnded)
    }
  }, [onEnded])

  // Play/pause control
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    if (isPlaying) {
      audio.play().catch(console.error)
    } else {
      audio.pause()
    }
  }, [isPlaying])

  // Handle canvas click for seeking with improved precision
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    const audio = audioRef.current
    if (!canvas || !audio || !duration) return

    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    // Ensure we stay within bounds
    const clampedX = Math.max(0, Math.min(x, rect.width))
    const progress = clampedX / rect.width
    const newTime = Math.max(0, Math.min(progress * duration, duration))
    
    try {
      audio.currentTime = newTime
      setCurrentTime(newTime)
    } catch (error) {
      console.warn('Seek failed:', error)
    }
  }

  // Handle mouse move for precise seeking preview
  const [seekPreview, setSeekPreview] = useState<number | null>(null)
  
  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas || !duration) return

    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const clampedX = Math.max(0, Math.min(x, rect.width))
    const progress = clampedX / rect.width
    const previewTime = progress * duration
    setSeekPreview(previewTime)
  }

  const handleCanvasMouseLeave = () => {
    setSeekPreview(null)
  }

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="audio-player">
      <audio ref={audioRef} src={audioUrl} preload="metadata" />
      
      <button className="audio-player-close" onClick={onClose} title="Fermer le lecteur">
        ✕
      </button>
      
      <div className="audio-player-header">
        <button 
          className={`play-button ${isPlaying ? 'playing' : ''}`}
          onClick={isPlaying ? onPause : onPlay}
          disabled={isLoading}
        >
          {isLoading ? '⏳' : isPlaying ? '⏸️' : '▶️'}
        </button>
        
        <div className="track-info">
          <div className="track-title">{track.title}</div>
          <div className="track-artist">{track.artists}</div>
        </div>
        
        <div className="time-display">
          <span className="current-time">{formatTime(currentTime)}</span>
          <span className="separator">/</span>
          <span className="total-time">{formatTime(duration)}</span>
          {seekPreview !== null && (
            <span className="seek-preview">→ {formatTime(seekPreview)}</span>
          )}
        </div>
      </div>

      <div className="waveform-container">
        <div className="progress-bar-precise">
          <div 
            className="progress-bar-fill" 
            style={{ width: `${duration ? (currentTime / duration) * 100 : 0}%` }}
          />
          <div 
            className="progress-bar-handle" 
            style={{ left: `${duration ? (currentTime / duration) * 100 : 0}%` }}
          />
          {seekPreview !== null && (
            <div 
              className="progress-bar-preview" 
              style={{ left: `${duration ? (seekPreview / duration) * 100 : 0}%` }}
            />
          )}
        </div>
        <canvas
          ref={canvasRef}
          width={600}
          height={60}
          className="waveform-canvas"
          onClick={handleCanvasClick}
          onMouseMove={handleCanvasMouseMove}
          onMouseLeave={handleCanvasMouseLeave}
          style={{ cursor: 'pointer' }}
        />
        {isLoading && (
          <div className="waveform-loading">Loading waveform...</div>
        )}
      </div>
    </div>
  )
}

export default AudioPlayer