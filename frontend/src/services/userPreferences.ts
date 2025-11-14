/**
 * User Preferences Service
 * 
 * Manages user preferences stored in localStorage
 */

const STORAGE_PREFIX = 'music_downloader_';

export interface TrackColumnsVisibility {
  showIdColumn: boolean;
  showPositionColumn: boolean;
  showDownloadedColumn: boolean;
  showGenreColumn: boolean;
  showBpmColumn: boolean;
  showDurationColumn: boolean;
  showSpotifyAddedColumn: boolean;
  showPlaylistAddedColumn: boolean;
  showPlaylistsColumn: boolean;
}

export interface UserPreferences {
  trackColumnsVisibility: TrackColumnsVisibility;
}

const DEFAULT_PREFERENCES: UserPreferences = {
  trackColumnsVisibility: {
    showIdColumn: false,
    showPositionColumn: false,
    showDownloadedColumn: false,
    showGenreColumn: false,
    showBpmColumn: false,
    showDurationColumn: false,
    showSpotifyAddedColumn: false,
    showPlaylistAddedColumn: false,
    showPlaylistsColumn: false,
  },
};

class UserPreferencesService {
  private getStorageKey(key: string): string {
    return `${STORAGE_PREFIX}${key}`;
  }

  /**
   * Get all user preferences
   */
  getPreferences(): UserPreferences {
    try {
      const stored = localStorage.getItem(this.getStorageKey('preferences'));
      if (stored) {
        const parsed = JSON.parse(stored);
        // Merge with defaults to handle new preferences
        return {
          ...DEFAULT_PREFERENCES,
          ...parsed,
          trackColumnsVisibility: {
            ...DEFAULT_PREFERENCES.trackColumnsVisibility,
            ...(parsed.trackColumnsVisibility || {}),
          },
        };
      }
    } catch (error) {
      console.error('Error loading user preferences:', error);
    }
    return DEFAULT_PREFERENCES;
  }

  /**
   * Save all user preferences
   */
  setPreferences(preferences: UserPreferences): void {
    try {
      localStorage.setItem(
        this.getStorageKey('preferences'),
        JSON.stringify(preferences)
      );
    } catch (error) {
      console.error('Error saving user preferences:', error);
    }
  }

  /**
   * Get track columns visibility preferences
   */
  getTrackColumnsVisibility(): TrackColumnsVisibility {
    return this.getPreferences().trackColumnsVisibility;
  }

  /**
   * Save track columns visibility preferences
   */
  setTrackColumnsVisibility(visibility: TrackColumnsVisibility): void {
    const preferences = this.getPreferences();
    preferences.trackColumnsVisibility = visibility;
    this.setPreferences(preferences);
  }

  /**
   * Update a single column visibility preference
   */
  setColumnVisibility(columnKey: keyof TrackColumnsVisibility, visible: boolean): void {
    const preferences = this.getPreferences();
    preferences.trackColumnsVisibility[columnKey] = visible;
    this.setPreferences(preferences);
  }

  /**
   * Clear all preferences (reset to defaults)
   */
  clearPreferences(): void {
    try {
      localStorage.removeItem(this.getStorageKey('preferences'));
    } catch (error) {
      console.error('Error clearing user preferences:', error);
    }
  }
}

// Export singleton instance
export const userPreferences = new UserPreferencesService();
