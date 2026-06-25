import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api'

// ── Helpers ──
function timeAgo(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'now'
  if (mins < 60) return `${mins}m`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h`
  return `${Math.floor(hrs / 24)}d`
}

function getInitial(name) {
  return name ? name.charAt(0).toUpperCase() : '?'
}

function parseToken(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return { userId: payload.sub, username: payload.username }
  } catch { return null }
}

// ── Auth Page ──
function AuthPage({ onLogin }) {
  const [isRegister, setIsRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    try {
      if (isRegister) {
        await api.register(username, email, password)
      }
      const data = await api.login(username, password)
      localStorage.setItem('token', data.access_token)
      onLogin(data.access_token)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="auth-page">
      <h2>🐦 Mini Twitter</h2>
      <form className="auth-form" onSubmit={handleSubmit}>
        <input placeholder="Username" value={username}
          onChange={e => setUsername(e.target.value)} required />
        {isRegister && (
          <input placeholder="Email" type="email" value={email}
            onChange={e => setEmail(e.target.value)} required />
        )}
        <input placeholder="Password" type="password" value={password}
          onChange={e => setPassword(e.target.value)} required />
        <button type="submit">{isRegister ? 'Register' : 'Login'}</button>
        {error && <p className="error">{error}</p>}
      </form>
      <p className="auth-toggle">
        {isRegister ? 'Already have an account? ' : "Don't have an account? "}
        <span onClick={() => { setIsRegister(!isRegister); setError('') }}>
          {isRegister ? 'Login' : 'Register'}
        </span>
      </p>
    </div>
  )
}

// ── Tweet Box ──
function TweetBox({ token, onTweeted }) {
  const [content, setContent] = useState('')
  const [posting, setPosting] = useState(false)
  const [error, setError] = useState('')

  async function handlePost() {
    if (!content.trim() || content.length > 280) return
    setPosting(true)
    setError('')
    try {
      await api.createTweet(content.trim(), token)
      setContent('')
      onTweeted()
    } catch (err) {
      setError(err.message)
    }
    setPosting(false)
  }

  return (
    <div className="tweet-box">
      <textarea rows={3} placeholder="What's happening?"
        value={content} onChange={e => setContent(e.target.value)} />
      <div className="tweet-box-footer">
        <span className={`char-count ${content.length > 280 ? 'over' : ''}`}>
          {content.length}/280
        </span>
        <button onClick={handlePost}
          disabled={posting || !content.trim() || content.length > 280}>
          {posting ? 'Posting...' : 'Tweet'}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  )
}

// ── Tweet Card ──
function Tweet({ tweet, currentUserId, token, onDelete, onViewProfile }) {
  const isOwner = tweet.user_id === currentUserId
  const displayName = tweet.username || tweet.user_id?.slice(0, 8)

  async function handleDelete() {
    const tweetId = tweet.id || tweet.tweet_id
    if (!confirm('Delete this tweet?')) return
    try {
      await api.deleteTweet(tweetId, token)
      onDelete()
    } catch (err) {
      alert(err.message)
    }
  }

  return (
    <div className="tweet">
      <div className="tweet-avatar">{getInitial(displayName)}</div>
      <div className="tweet-body">
        <div className="tweet-header">
          <span className="tweet-username"
            onClick={() => onViewProfile(tweet.user_id)}>
            @{displayName}
          </span>
          <span className="tweet-time">{timeAgo(tweet.created_at)}</span>
        </div>
        <div className="tweet-content">{tweet.content}</div>
        {isOwner && (
          <div className="tweet-actions">
            <button onClick={handleDelete}>Delete</button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── User Search ──
function UserSearch({ onViewProfile }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const debounceRef = useRef(null)

  function handleChange(e) {
    const val = e.target.value
    setQuery(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!val.trim()) { setResults([]); return }
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      try {
        const users = await api.searchUsers(val.trim())
        setResults(users)
      } catch { setResults([]) }
      setSearching(false)
    }, 300)
  }

  return (
    <div className="search-bar">
      <input placeholder="Search users by username..."
        value={query} onChange={handleChange} />
      {query.trim() && (
        <div className="search-results">
          {searching && <div className="loading" style={{padding: '10px'}}>Searching...</div>}
          {!searching && results.length === 0 && query.trim() && (
            <div className="empty" style={{padding: '10px'}}>No users found</div>
          )}
          {results.map(u => (
            <div key={u.id} className="search-item" onClick={() => {
              onViewProfile(u.id)
              setQuery('')
              setResults([])
            }}>
              <div className="search-item-left">
                <div className="tweet-avatar">{getInitial(u.username)}</div>
                <div>
                  <div style={{ fontWeight: 500 }}>@{u.username}</div>
                  <div style={{ fontSize: 12, color: '#999' }}>{u.follower_count} followers</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Profile Page ──
function ProfilePage({ userId, token, currentUserId, onBack, onViewProfile }) {
  const [profile, setProfile] = useState(null)
  const [tweets, setTweets] = useState([])
  const [isFollowing, setIsFollowing] = useState(false)
  const [followers, setFollowers] = useState([])
  const [following, setFollowing] = useState([])
  const [tab, setTab] = useState('tweets')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const p = await api.getProfile(userId)
      setProfile(p)
      const tl = await api.userTimeline(userId, 50)
      setTweets(tl.tweets || [])
      if (currentUserId && currentUserId !== userId) {
        const fData = await api.getFollowers(userId, 100)
        const ids = (fData.users || []).map(u => u.id)
        setIsFollowing(ids.includes(currentUserId))
      }
    } catch (err) {
      setError(err.message)
    }
  }, [userId, currentUserId])

  useEffect(() => { load() }, [load])

  async function loadFollowers() {
    const data = await api.getFollowers(userId, 50)
    setFollowers(data.users || [])
    setTab('followers')
  }

  async function loadFollowing() {
    const data = await api.getFollowing(userId, 50)
    setFollowing(data.users || [])
    setTab('following')
  }

  async function handleFollow() {
    try { await api.follow(userId, token); setIsFollowing(true); load() }
    catch (err) { alert(err.message) }
  }

  async function handleUnfollow() {
    try { await api.unfollow(userId, token); setIsFollowing(false); load() }
    catch (err) { alert(err.message) }
  }

  if (error) return (
    <div>
      <div style={{padding: '16px'}}><button className="btn-back" onClick={onBack}>← Back</button></div>
      <div className="error" style={{padding: 20}}>{error}</div>
    </div>
  )
  if (!profile) return <div className="loading">Loading...</div>

  return (
    <div>
      <div className="profile-header">
        <button className="btn-back" onClick={onBack}>← Back</button>
        <div className="profile-info">
          <div className="profile-avatar">{getInitial(profile.username)}</div>
          <div className="profile-details">
            <h3>@{profile.username}</h3>
            <p>{profile.email}</p>
          </div>
        </div>
        <div className="profile-stats">
          <span><strong>{profile.follower_count}</strong> followers</span>
        </div>
        {currentUserId && currentUserId !== userId && (
          <div className="profile-actions">
            {isFollowing ? (
              <button className="btn-unfollow" onClick={handleUnfollow}>Unfollow</button>
            ) : (
              <button className="btn-follow" onClick={handleFollow}>Follow</button>
            )}
          </div>
        )}
      </div>

      <div className="tabs">
        <button className={tab === 'tweets' ? 'active' : ''} onClick={() => setTab('tweets')}>Tweets</button>
        <button className={tab === 'followers' ? 'active' : ''} onClick={loadFollowers}>Followers</button>
        <button className={tab === 'following' ? 'active' : ''} onClick={loadFollowing}>Following</button>
      </div>

      {tab === 'tweets' && (
        tweets.length === 0
          ? <div className="empty">No tweets yet</div>
          : tweets.map((t, i) => (
            <Tweet key={t.id || i} tweet={t} currentUserId={currentUserId}
              token={token} onDelete={load} onViewProfile={onViewProfile} />
          ))
      )}

      {tab === 'followers' && (
        followers.length === 0
          ? <div className="empty">No followers</div>
          : followers.map(u => (
            <div key={u.id} className="search-item" onClick={() => onViewProfile(u.id)}>
              <div className="search-item-left">
                <div className="tweet-avatar">{getInitial(u.username)}</div>
                <span style={{ fontWeight: 500 }}>@{u.username}</span>
              </div>
            </div>
          ))
      )}

      {tab === 'following' && (
        following.length === 0
          ? <div className="empty">Not following anyone</div>
          : following.map(u => (
            <div key={u.id} className="search-item" onClick={() => onViewProfile(u.id)}>
              <div className="search-item-left">
                <div className="tweet-avatar">{getInitial(u.username)}</div>
                <span style={{ fontWeight: 500 }}>@{u.username}</span>
              </div>
            </div>
          ))
      )}
    </div>
  )
}

// ── Main App ──
export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || '')
  const [user, setUser] = useState(null)
  const [page, setPage] = useState('home')
  const [profileUserId, setProfileUserId] = useState(null)
  const [tweets, setTweets] = useState([])

  useEffect(() => {
    if (token) {
      const parsed = parseToken(token)
      if (parsed) setUser(parsed)
      else { setToken(''); localStorage.removeItem('token') }
    }
  }, [token])

  const loadTimeline = useCallback(async () => {
    if (!token || !user) return
    try {
      const data = await api.homeTimeline(token, 50)
      setTweets(data.tweets || [])
    } catch (err) {
      console.error('Timeline error:', err)
      if (err.message.includes('expired') || err.message.includes('Invalid')) {
        handleLogout()
      }
    }
  }, [token, user])

  useEffect(() => {
    if (token && user && page === 'home') loadTimeline()
  }, [token, user, page, loadTimeline])

  function handleLogin(newToken) { setToken(newToken) }

  function handleLogout() {
    setToken(''); setUser(null)
    localStorage.removeItem('token')
    setPage('home')
  }

  function viewProfile(userId) {
    setProfileUserId(userId)
    setPage('profile')
  }

  if (!token) return <AuthPage onLogin={handleLogin} />

  return (
    <div className="app">
      <div className="navbar">
        <h2 onClick={() => setPage('home')} style={{ cursor: 'pointer' }}>🐦 Mini Twitter</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="nav-user" style={{ cursor: 'pointer' }}
            onClick={() => viewProfile(user?.userId)}>
            @{user?.username}
          </span>
          <button onClick={handleLogout}>Logout</button>
        </div>
      </div>

      {page === 'profile' ? (
        <ProfilePage userId={profileUserId} token={token}
          currentUserId={user?.userId} onBack={() => setPage('home')}
          onViewProfile={viewProfile} />
      ) : (
        <div>
          <TweetBox token={token} onTweeted={loadTimeline} />
          <UserSearch onViewProfile={viewProfile} />

          <div style={{ padding: '8px 16px', fontSize: 13, color: '#999', borderBottom: '1px solid #e0e0e0' }}>
            <strong style={{ color: '#333' }}>Home Timeline</strong>
            {' · '}
            <span style={{ cursor: 'pointer', color: '#1a8cd8' }} onClick={loadTimeline}>Refresh</span>
          </div>

          {tweets.length === 0
            ? <div className="empty">No tweets yet. Post something or follow users!</div>
            : tweets.map((t, i) => (
              <Tweet key={t.id || i} tweet={t} currentUserId={user?.userId}
                token={token} onDelete={loadTimeline} onViewProfile={viewProfile} />
            ))
          }
        </div>
      )}
    </div>
  )
}
