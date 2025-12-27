import React from 'react'

type Download = {
  id: number
  track_id: number
  candidate_id?: number | null
  provider: string
  status: string
  filepath?: string | null
  format?: string | null
  bitrate_kbps?: number | null
  filesize_bytes?: number | null
  error_message?: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  track_title?: string
  track_artists?: string
}

type WorkerStatus = {
  worker_running: boolean
  queue_size: number
  active_tasks: number
  concurrency: number
}

type LogsResponse = {
  lines: string[]
  count: number
  max_lines: number
  size_kb: number
}

export const DownloadsPage: React.FC = () => {
  const [items, setItems] = React.useState<Download[]>([])
  const [loading, setLoading] = React.useState(false)
  const [enqueueTrackId, setEnqueueTrackId] = React.useState('')
  const [enqueueCandidateId, setEnqueueCandidateId] = React.useState('')
  const [trackQuery, setTrackQuery] = React.useState('')
  const [trackOptions, setTrackOptions] = React.useState<any[]>([])
  
  // Worker status and logs
  const [workerStatus, setWorkerStatus] = React.useState<WorkerStatus | null>(null)
  const [logs, setLogs] = React.useState<LogsResponse | null>(null)
  const [showLogs, setShowLogs] = React.useState(false)
  const [autoRefresh, setAutoRefresh] = React.useState(true)
  const logsContainerRef = React.useRef<HTMLDivElement>(null)
  const [logsAutoScroll, setLogsAutoScroll] = React.useState(true)

  const load = React.useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/api/v1/downloads/with_tracks?limit=200')
      if (!r.ok) return
      setItems(await r.json())
      // Auto-cleanup old downloads (keep only recent)
      fetch('/api/v1/downloads/cleanup', { method: 'POST' }).catch(() => {})
    } finally {
      setLoading(false)
    }
  }, [])

  const loadWorkerStatus = React.useCallback(async () => {
    try {
      const r = await fetch('/api/v1/downloads/status')
      if (r.ok) setWorkerStatus(await r.json())
    } catch {}
  }, [])

  const loadLogs = React.useCallback(async () => {
    try {
      const r = await fetch('/api/v1/downloads/logs')
      if (r.ok) {
        const data = await r.json()
        setLogs(data)
        // Auto-scroll to bottom only within the logs container (not the page)
        if (logsAutoScroll && logsContainerRef.current) {
          setTimeout(() => {
            if (logsContainerRef.current) {
              logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight
            }
          }, 50)
        }
      }
    } catch {}
  }, [logsAutoScroll])

  React.useEffect(() => { load(); loadWorkerStatus() }, [load, loadWorkerStatus])

  // Smart auto-refresh: poll when there are pending/running downloads
  React.useEffect(() => {
    if (!autoRefresh) return
    
    const hasPending = items.some(d => d.status === 'queued' || d.status === 'running')
    if (!hasPending) return
    
    const interval = setInterval(() => {
      load()
      loadWorkerStatus()
      if (showLogs) loadLogs()
    }, 2000)
    
    return () => clearInterval(interval)
  }, [autoRefresh, items, showLogs, load, loadWorkerStatus, loadLogs])

  // Lookup tracks by text (title/artists)
  const searchTracks = React.useCallback(async () => {
    if (!trackQuery || trackQuery.length < 2) { setTrackOptions([]); return }
    const r = await fetch('/api/v1/tracks?q=' + encodeURIComponent(trackQuery) + '&limit=10')
    if (r.ok) setTrackOptions(await r.json())
  }, [trackQuery])
  React.useEffect(() => { const id = setTimeout(searchTracks, 250); return () => clearTimeout(id) }, [trackQuery, searchTracks])

  const enqueue = async () => {
    const params = new URLSearchParams({ track_id: enqueueTrackId })
    if (enqueueCandidateId) params.set('candidate_id', enqueueCandidateId)
    const r = await fetch('/api/v1/downloads/enqueue?' + params.toString(), { method: 'POST' })
    if (r.ok) {
      setEnqueueTrackId('')
      setEnqueueCandidateId('')
      load()
    }
  }

  const cancelDownload = async (id: number) => {
    const r = await fetch(`/api/v1/downloads/cancel/${id}`, { method: 'POST' })
    if (r.ok) {
      load()
      return
    }
    if (r.status === 409) {
      alert('This job is already running and cannot be cancelled.')
      load()
      return
    }
    alert('Cancel failed: ' + r.status)
  }

  const stopAllDownloads = async () => {
    if (!confirm('Stop all downloads? Queued downloads will be marked as skipped.')) return
    try {
      const r = await fetch('/api/v1/downloads/stop_all', { method: 'POST' })
      if (r.ok) {
        const data = await r.json()
        alert(`Stopped successfully!\nQueued downloads skipped: ${data.queued_skipped}\nWorker stopped: ${data.worker_stopped}`)
        load()
      } else {
        alert('Failed to stop downloads: ' + r.status)
      }
    } catch (e) {
      console.error('Stop all error:', e)
      alert('Error stopping downloads')
    }
  }

  const restartWorker = async () => {
    if (!confirm('Restart the download worker? This will stop current downloads and restart the worker.')) return
    try {
      const r = await fetch('/api/v1/downloads/restart_worker', { method: 'POST' })
      if (r.ok) {
        alert('Download worker restarted successfully!')
        load()
        loadWorkerStatus()
      } else {
        alert('Failed to restart worker: ' + r.status)
      }
    } catch (e) {
      console.error('Restart worker error:', e)
      alert('Error restarting worker')
    }
  }

  const clearLogs = async () => {
    try {
      await fetch('/api/v1/downloads/logs/clear', { method: 'POST' })
      loadLogs()
    } catch {}
  }

  const toggleLogs = () => {
    if (!showLogs) {
      loadLogs()
    }
    setShowLogs(!showLogs)
  }

  // Count downloads by status
  const activeDownloads = items.filter(d => d.status === 'queued' || d.status === 'running')
  const completedDownloads = items.filter(d => d.status !== 'queued' && d.status !== 'running').slice(0, 50)
  const runningCount = items.filter(d => d.status === 'running').length
  const queuedCount = items.filter(d => d.status === 'queued').length

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <h2 style={{ margin: 0 }}>Downloads</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {workerStatus && (
            <span style={{ fontSize: '0.85em', color: workerStatus.worker_running ? '#4caf50' : '#f44336', marginRight: 8 }}>
              Worker: {workerStatus.worker_running ? `Running (${workerStatus.active_tasks}/${workerStatus.concurrency} tasks, ${workerStatus.queue_size} queued)` : 'Stopped'}
            </span>
          )}
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.9em' }}>
            <input type='checkbox' checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
            Auto-refresh {activeDownloads.length > 0 && <span style={{ color: '#2196f3' }}>({activeDownloads.length} active)</span>}
          </label>
          <button onClick={toggleLogs} style={{ background: showLogs ? '#2196f3' : '#9e9e9e', color: 'white', border: 'none', padding: '8px 16px', borderRadius: 4, cursor: 'pointer' }}>
            {showLogs ? 'Hide Logs' : 'Show Logs'}
          </button>
          <button onClick={stopAllDownloads} style={{ background: '#f44336', color: 'white', border: 'none', padding: '8px 16px', borderRadius: 4, cursor: 'pointer' }}>
            Stop All Downloads
          </button>
          <button onClick={restartWorker} style={{ background: '#ff9800', color: 'white', border: 'none', padding: '8px 16px', borderRadius: 4, cursor: 'pointer' }}>
            Restart Worker
          </button>
        </div>
      </div>

      {/* Worker Logs Panel */}
      {showLogs && (
        <div style={{ border: '1px solid #333', borderRadius: 6, background: '#1e1e1e', overflow: 'hidden' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: '#333', borderBottom: '1px solid #444' }}>
            <span style={{ color: '#fff', fontWeight: 500 }}>
              Worker Logs {logs && <span style={{ color: '#888', fontSize: '0.85em' }}>({logs.count}/{logs.max_lines} lines, {logs.size_kb} KB)</span>}
            </span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.8em', color: '#aaa' }}>
                <input type='checkbox' checked={logsAutoScroll} onChange={e => setLogsAutoScroll(e.target.checked)} />
                Auto-scroll
              </label>
              <button onClick={loadLogs} style={{ background: '#555', color: 'white', border: 'none', padding: '4px 12px', borderRadius: 4, cursor: 'pointer', fontSize: '0.85em' }}>
                Refresh
              </button>
              <button onClick={clearLogs} style={{ background: '#666', color: 'white', border: 'none', padding: '4px 12px', borderRadius: 4, cursor: 'pointer', fontSize: '0.85em' }}>
                Clear
              </button>
            </div>
          </div>
          <div ref={logsContainerRef} style={{ maxHeight: 300, overflow: 'auto', padding: 12, fontFamily: 'monospace', fontSize: '0.85em', color: '#ddd', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {logs?.lines.length === 0 && <span style={{ color: '#888' }}>No logs yet.</span>}
            {logs?.lines.map((line, i) => {
              const isError = line.includes('[ERROR]')
              const isWarn = line.includes('[WARN]')
              return (
                <div key={i} style={{ color: isError ? '#f44336' : isWarn ? '#ff9800' : '#ddd', marginBottom: 2 }}>
                  {line}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Manual enqueue section */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', padding: '8px 12px', background: '#f5f5f5', borderRadius: 6 }}>
        <span style={{ fontSize: '0.9em', fontWeight: 500 }}>Manual enqueue:</span>
        <div style={{ position: 'relative', display: 'inline-block' }}>
          <input placeholder='Type title or artist' value={trackQuery} onChange={e => setTrackQuery(e.target.value)} style={{ minWidth: 240 }} />
          {trackOptions.length > 0 && (
            <div style={{ border: '1px solid #ddd', maxHeight: 180, overflow: 'auto', background: '#fff', position: 'absolute', zIndex: 1, top: '100%', left: 0, right: 0 }}>
              {trackOptions.map((t: any) => (
                <div key={t.id} style={{ padding: 6, cursor: 'pointer' }} onClick={() => { setEnqueueTrackId(String(t.id)); setTrackOptions([]); setTrackQuery(`${t.artists} - ${t.title}`) }}>
                  {t.artists} - {t.title}
                </div>
              ))}
            </div>
          )}
        </div>
        <input placeholder='Candidate ID (opt.)' value={enqueueCandidateId} onChange={e => setEnqueueCandidateId(e.target.value)} style={{ width: 120 }} />
        <button onClick={enqueue} disabled={!enqueueTrackId}>Enqueue</button>
      </div>

      {/* Active Downloads - Running + Queued */}
      {activeDownloads.length > 0 && (
        <div style={{ border: '2px solid #2196f3', borderRadius: 6, overflow: 'hidden' }}>
          <h3 style={{ margin: 0, padding: 12, background: '#2196f3', color: 'white', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Active Downloads</span>
            <span style={{ fontSize: '0.85em', fontWeight: 400 }}>
              {runningCount} running, {queuedCount} queued
            </span>
          </h3>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ textAlign: 'left', background: '#e3f2fd' }}>
                <th style={{ padding: '8px 12px', borderBottom: '1px solid #bbdefb' }}>Track</th>
                <th style={{ padding: '8px 12px', borderBottom: '1px solid #bbdefb' }}>Status</th>
                <th style={{ padding: '8px 12px', borderBottom: '1px solid #bbdefb' }}>Started</th>
                <th style={{ padding: '8px 12px', borderBottom: '1px solid #bbdefb' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {activeDownloads.map(d => {
                const statusColor = d.status === 'running' ? '#2196f3' : '#ff9800'
                const canCancel = d.status === 'queued'
                return (
                  <tr key={d.id} style={{ borderBottom: '1px solid #e3f2fd' }}>
                    <td style={{ padding: '8px 12px' }}>
                      <div style={{ fontWeight: 500 }}>{d.track_artists ?? 'Unknown'}</div>
                      <div style={{ fontSize: '0.9em', color: '#666' }}>{d.track_title ?? 'Unknown Title'}</div>
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      <span style={{ 
                        padding: '4px 8px', 
                        borderRadius: 4, 
                        background: statusColor + '20',
                        color: statusColor,
                        fontSize: '0.9em',
                        fontWeight: 500
                      }}>
                        {d.status === 'running' ? '⏳ downloading…' : '⏸ queued'}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', fontSize: '0.9em', color: '#666' }}>
                      {d.started_at ? new Date(d.started_at).toLocaleTimeString() : '-'}
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      {canCancel && (
                        <button 
                          onClick={() => cancelDownload(d.id)}
                          style={{ 
                            background: '#f44336', 
                            color: 'white', 
                            border: 'none', 
                            padding: '4px 12px', 
                            borderRadius: 4, 
                            cursor: 'pointer',
                            fontSize: '0.85em'
                          }}
                        >
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Completed Downloads History */}
      <div style={{ border: '1px solid #ddd', borderRadius: 6, overflow: 'hidden' }}>
        <h3 style={{ margin: 0, padding: 12, background: '#f5f5f5', borderBottom: '1px solid #ddd', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Recent History</span>
          <span style={{ fontSize: '0.85em', fontWeight: 400, color: '#666' }}>
            Last {completedDownloads.length} completed
          </span>
        </h3>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', background: '#fafafa' }}>
              <th style={{ padding: '8px 12px', borderBottom: '1px solid #ddd' }}>Track</th>
              <th style={{ padding: '8px 12px', borderBottom: '1px solid #ddd' }}>Status</th>
              <th style={{ padding: '8px 12px', borderBottom: '1px solid #ddd' }}>Time</th>
              <th style={{ padding: '8px 12px', borderBottom: '1px solid #ddd' }}>Error</th>
            </tr>
          </thead>
          <tbody>
            {completedDownloads.map(d => {
              const statusColor = d.status === 'done' ? '#4caf50' : d.status === 'failed' ? '#f44336' : d.status === 'already' ? '#9e9e9e' : '#ff9800'
              return (
                <tr key={d.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '8px 12px' }}>
                    <div style={{ fontWeight: 500 }}>{d.track_artists ?? 'Unknown'}</div>
                    <div style={{ fontSize: '0.9em', color: '#666' }}>{d.track_title ?? 'Unknown Title'}</div>
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <span style={{ 
                      padding: '4px 8px', 
                      borderRadius: 4, 
                      background: statusColor + '20',
                      color: statusColor,
                      fontSize: '0.9em',
                      fontWeight: 500
                    }}>
                      {d.status}
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px', fontSize: '0.9em', color: '#666' }}>
                    {d.finished_at ? new Date(d.finished_at).toLocaleString() : 
                     d.started_at ? new Date(d.started_at).toLocaleString() : 
                     new Date(d.created_at).toLocaleString()}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    {d.error_message ? (
                      <div style={{ 
                        color: '#f44336',
                        fontSize: '0.85em',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        maxWidth: 400
                      }}>
                        {d.error_message.length > 100 ? d.error_message.substring(0, 100) + '…' : d.error_message}
                      </div>
                    ) : '-'}
                  </td>
                </tr>
              )
            })}
            {completedDownloads.length === 0 && (
              <tr>
                <td colSpan={4} style={{ textAlign: 'center', padding: 20, color: '#999' }}>
                  No completed downloads yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default DownloadsPage
