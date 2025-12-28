import React from 'react'

type CookiesStatus = {
  configured: boolean
  file_path: string
  file_exists: boolean
  file_size: number | null
  line_count: number | null
}

type CookiesCheck = {
  valid: boolean
  found_required: string[]
  found_important: string[]
  missing_required: string[]
  total_cookies: number
  hint: string | null
  error?: string
}

type CookiesTest = {
  success: boolean
  message?: string
  error?: string
  details?: string
}

export const SettingsPage: React.FC = () => {
  const [cookiesStatus, setCookiesStatus] = React.useState<CookiesStatus | null>(null)
  const [cookiesCheck, setCookiesCheck] = React.useState<CookiesCheck | null>(null)
  const [cookiesTest, setCookiesTest] = React.useState<CookiesTest | null>(null)
  const [cookiesContent, setCookiesContent] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const [testing, setTesting] = React.useState(false)
  const [message, setMessage] = React.useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const loadCookiesStatus = React.useCallback(async () => {
    try {
      const [statusRes, checkRes] = await Promise.all([
        fetch('/api/v1/settings/cookies'),
        fetch('/api/v1/settings/cookies/check'),
      ])
      if (statusRes.ok) {
        setCookiesStatus(await statusRes.json())
      }
      if (checkRes.ok) {
        setCookiesCheck(await checkRes.json())
      }
    } catch {}
  }, [])

  React.useEffect(() => {
    loadCookiesStatus()
  }, [loadCookiesStatus])

  const handleUpload = async () => {
    if (!cookiesContent.trim()) {
      setMessage({ type: 'error', text: 'Please paste your cookies content' })
      return
    }

    setLoading(true)
    setMessage(null)

    try {
      const r = await fetch('/api/v1/settings/cookies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: cookiesContent }),
      })

      const data = await r.json()

      if (r.ok) {
        setMessage({ type: 'success', text: data.message || 'Cookies saved successfully' })
        setCookiesContent('')
        loadCookiesStatus()
      } else {
        setMessage({ type: 'error', text: data.detail || 'Failed to save cookies' })
      }
    } catch (e) {
      setMessage({ type: 'error', text: 'Network error' })
    } finally {
      setLoading(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setCookiesTest(null)

    try {
      const r = await fetch('/api/v1/settings/cookies/test', { method: 'POST' })
      const data = await r.json()
      setCookiesTest(data)
    } catch (e) {
      setCookiesTest({ success: false, error: 'Network error' })
    } finally {
      setTesting(false)
    }
  }

  const handleDelete = async () => {
    if (!confirm('Delete YouTube cookies? Downloads requiring authentication will fail.')) return

    setLoading(true)
    setMessage(null)

    try {
      const r = await fetch('/api/v1/settings/cookies', { method: 'DELETE' })
      const data = await r.json()

      if (r.ok) {
        setMessage({ type: 'success', text: data.message || 'Cookies deleted' })
        loadCookiesStatus()
      } else {
        setMessage({ type: 'error', text: data.detail || 'Failed to delete cookies' })
      }
    } catch (e) {
      setMessage({ type: 'error', text: 'Network error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 800 }}>
      <h2 style={{ margin: 0 }}>Settings</h2>

      {/* YouTube Cookies Section */}
      <div style={{ border: '1px solid #ddd', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{ background: '#f5f5f5', padding: '12px 16px', borderBottom: '1px solid #ddd' }}>
          <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span>🍪</span>
            YouTube Cookies
            {cookiesStatus?.configured && (
              <span style={{ 
                fontSize: '0.75em', 
                background: '#4caf50', 
                color: 'white', 
                padding: '2px 8px', 
                borderRadius: 12,
                fontWeight: 500
              }}>
                Configured
              </span>
            )}
          </h3>
        </div>

        <div style={{ padding: 16 }}>
          <p style={{ margin: '0 0 12px', color: '#666', fontSize: '0.9em' }}>
            Some YouTube videos require authentication (age-restricted content). 
            Upload your browser cookies to enable downloading these videos.
          </p>

          {/* Current Status */}
          {cookiesStatus && (
            <div style={{ 
              background: cookiesStatus.configured ? '#e8f5e9' : '#fff3e0', 
              padding: 12, 
              borderRadius: 6,
              marginBottom: 16,
              fontSize: '0.9em'
            }}>
              <div><strong>Status:</strong> {cookiesStatus.configured ? '✅ Configured' : '⚠️ Not configured'}</div>
              {cookiesStatus.file_exists && (
                <>
                  <div><strong>Cookie entries:</strong> {cookiesStatus.line_count ?? 'Unknown'}</div>
                  <div><strong>File size:</strong> {cookiesStatus.file_size ? `${(cookiesStatus.file_size / 1024).toFixed(1)} KB` : 'Unknown'}</div>
                </>
              )}
            </div>
          )}

          {/* Cookie Validation */}
          {cookiesCheck && cookiesStatus?.configured && (
            <div style={{ 
              background: cookiesCheck.valid ? '#e8f5e9' : '#ffebee', 
              padding: 12, 
              borderRadius: 6,
              marginBottom: 16,
              fontSize: '0.9em',
              border: `1px solid ${cookiesCheck.valid ? '#a5d6a7' : '#ef9a9a'}`
            }}>
              <div style={{ fontWeight: 500, marginBottom: 8 }}>
                {cookiesCheck.valid ? '✅ Authentication cookies found' : '❌ Missing authentication cookies'}
              </div>
              {cookiesCheck.found_required.length > 0 && (
                <div style={{ color: '#2e7d32', marginBottom: 4 }}>
                  <strong>Found:</strong> {cookiesCheck.found_required.join(', ')}
                </div>
              )}
              {cookiesCheck.missing_required.length > 0 && (
                <div style={{ color: '#c62828', marginBottom: 4 }}>
                  <strong>Missing:</strong> {cookiesCheck.missing_required.join(', ')}
                </div>
              )}
              {cookiesCheck.hint && (
                <div style={{ color: '#e65100', marginTop: 8, fontSize: '0.9em' }}>
                  💡 {cookiesCheck.hint}
                </div>
              )}
              <div style={{ color: '#666', marginTop: 8, fontSize: '0.85em' }}>
                Total cookies in file: {cookiesCheck.total_cookies}
              </div>
            </div>
          )}

          {/* Test Cookies Button */}
          {cookiesStatus?.configured && (
            <div style={{ marginBottom: 16 }}>
              <button
                onClick={handleTest}
                disabled={testing}
                style={{
                  background: '#ff9800',
                  color: 'white',
                  border: 'none',
                  padding: '8px 16px',
                  borderRadius: 6,
                  cursor: testing ? 'wait' : 'pointer',
                  opacity: testing ? 0.6 : 1,
                  fontWeight: 500,
                  fontSize: '0.9em',
                }}
              >
                {testing ? 'Testing...' : '🧪 Test Cookies with yt-dlp'}
              </button>
              <span style={{ marginLeft: 8, color: '#666', fontSize: '0.85em' }}>
                Tests against an age-restricted video
              </span>

              {cookiesTest && (
                <div style={{ 
                  marginTop: 8,
                  padding: 12, 
                  borderRadius: 6,
                  background: cookiesTest.success ? '#e8f5e9' : '#ffebee',
                  border: `1px solid ${cookiesTest.success ? '#a5d6a7' : '#ef9a9a'}`,
                  fontSize: '0.9em'
                }}>
                  {cookiesTest.success ? (
                    <div style={{ color: '#2e7d32' }}>
                      ✅ {cookiesTest.message || 'Cookies are working!'}
                    </div>
                  ) : (
                    <>
                      <div style={{ color: '#c62828', fontWeight: 500 }}>
                        ❌ {cookiesTest.error || 'Authentication failed'}
                      </div>
                      {cookiesTest.details && (
                        <pre style={{ 
                          margin: '8px 0 0', 
                          padding: 8, 
                          background: '#f5f5f5', 
                          borderRadius: 4,
                          fontSize: '0.8em',
                          overflow: 'auto',
                          maxHeight: 150,
                          whiteSpace: 'pre-wrap'
                        }}>
                          {cookiesTest.details}
                        </pre>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Instructions */}
          <details style={{ marginBottom: 16 }}>
            <summary style={{ cursor: 'pointer', fontWeight: 500, color: '#1976d2' }}>
              How to export cookies from your browser
            </summary>
            <div style={{ padding: '12px 0', fontSize: '0.9em', color: '#666' }}>
              <div style={{ background: '#fff3e0', padding: 12, borderRadius: 6, marginBottom: 12 }}>
                <strong>⚠️ Important:</strong> YouTube authentication cookies are <strong>HttpOnly</strong>, 
                which means JavaScript cannot access them. You <strong>must use a browser extension</strong> to export them.
              </div>

              <p style={{ margin: '0 0 12px', fontWeight: 500 }}>Recommended browser extensions:</p>
              <ul style={{ margin: '0 0 12px', paddingLeft: 20 }}>
                <li><strong>Chrome/Edge:</strong> <a href="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc" target="_blank" rel="noopener noreferrer">Get cookies.txt LOCALLY</a></li>
                <li><strong>Firefox:</strong> <a href="https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/" target="_blank" rel="noopener noreferrer">cookies.txt</a></li>
              </ul>

              <p style={{ margin: '0 0 8px', fontWeight: 500 }}>Steps:</p>
              <ol style={{ margin: 0, paddingLeft: 20 }}>
                <li>Install the extension for your browser</li>
                <li>Go to <a href="https://www.youtube.com" target="_blank" rel="noopener noreferrer">youtube.com</a> and make sure you're <strong>logged in</strong></li>
                <li>Click the extension icon and export cookies for youtube.com</li>
                <li>Copy the content and paste it below</li>
              </ol>

              <p style={{ margin: '16px 0 8px', fontWeight: 500 }}>Required cookies (must be present):</p>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                <li><code>__Secure-1PSID</code> - Main authentication cookie</li>
                <li><code>__Secure-3PSID</code> - Secondary auth</li>
                <li><code>LOGIN_INFO</code> - Login state</li>
              </ul>

              <p style={{ margin: '12px 0 0', padding: 8, background: '#e3f2fd', borderRadius: 4 }}>
                💡 <strong>Tip:</strong> After saving cookies, you may need to <strong>restart the container</strong> for them to take effect. 
                Cookies typically expire after a few weeks and need to be re-exported.
              </p>
            </div>
          </details>

          {/* Upload Form */}
          <div style={{ display: 'grid', gap: 12 }}>
            <textarea
              value={cookiesContent}
              onChange={e => setCookiesContent(e.target.value)}
              placeholder="Paste your cookies.txt content here (Netscape format)..."
              style={{
                width: '100%',
                minHeight: 150,
                padding: 12,
                borderRadius: 6,
                border: '1px solid #ddd',
                fontFamily: 'monospace',
                fontSize: '0.85em',
                resize: 'vertical',
              }}
            />

            {message && (
              <div style={{
                padding: 12,
                borderRadius: 6,
                background: message.type === 'success' ? '#e8f5e9' : '#ffebee',
                color: message.type === 'success' ? '#2e7d32' : '#c62828',
              }}>
                {message.text}
              </div>
            )}

            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={handleUpload}
                disabled={loading || !cookiesContent.trim()}
                style={{
                  background: '#1976d2',
                  color: 'white',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: 6,
                  cursor: loading ? 'wait' : 'pointer',
                  opacity: loading || !cookiesContent.trim() ? 0.6 : 1,
                  fontWeight: 500,
                }}
              >
                {loading ? 'Saving...' : 'Save Cookies'}
              </button>

              {cookiesStatus?.configured && (
                <button
                  onClick={handleDelete}
                  disabled={loading}
                  style={{
                    background: '#f44336',
                    color: 'white',
                    border: 'none',
                    padding: '10px 20px',
                    borderRadius: 6,
                    cursor: loading ? 'wait' : 'pointer',
                    opacity: loading ? 0.6 : 1,
                    fontWeight: 500,
                  }}
                >
                  Delete Cookies
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Other Settings can be added here */}
      <div style={{ color: '#999', fontSize: '0.85em', textAlign: 'center', padding: 16 }}>
        More settings coming soon...
      </div>
    </div>
  )
}

export default SettingsPage
