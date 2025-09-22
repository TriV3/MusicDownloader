import React from 'react'
import { useAudioPlayer } from '../contexts/AudioPlayerContext'
import AudioPlayer from './AudioPlayer'

export const GlobalAudioPlayer: React.FC = () => {
  const { currentTrack, isPlaying, audioUrl, togglePlayPause, stopTrack } = useAudioPlayer()

  if (!currentTrack || !audioUrl) {
    return null
  }

  return (
    <AudioPlayer
      track={currentTrack}
      audioUrl={audioUrl}
      isPlaying={isPlaying}
      onPlay={togglePlayPause}
      onPause={togglePlayPause}
      onEnded={stopTrack}
      onClose={stopTrack}
    />
  )
}

export default GlobalAudioPlayer