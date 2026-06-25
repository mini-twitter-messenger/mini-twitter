const API = '';

async function request(method, path, body = null, token = null) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API}${path}`, opts);
  if (res.status === 204) return null;
  const data = await res.json();
  if (!res.ok) {
    const msg = data?.detail?.detail || data?.detail || 'Request failed';
    throw new Error(msg);
  }
  return data;
}

export const api = {
  register: (username, email, password) =>
    request('POST', '/users/register', { username, email, password }),
  login: (username, password) =>
    request('POST', '/users/login', { username, password }),
  getProfile: (userId) =>
    request('GET', `/users/${userId}/profile`),
  follow: (userId, token) =>
    request('POST', `/users/${userId}/follow`, null, token),
  unfollow: (userId, token) =>
    request('DELETE', `/users/${userId}/follow`, null, token),
  getFollowers: (userId, limit = 20, offset = 0) =>
    request('GET', `/users/${userId}/followers?limit=${limit}&offset=${offset}`),
  getFollowing: (userId, limit = 20, offset = 0) =>
    request('GET', `/users/${userId}/following?limit=${limit}&offset=${offset}`),
  createTweet: (content, token) =>
    request('POST', '/tweets/', { content }, token),
  deleteTweet: (tweetId, token) =>
    request('DELETE', `/tweets/${tweetId}`, null, token),
  getTweet: (tweetId) =>
    request('GET', `/tweets/${tweetId}`),
  homeTimeline: (token, limit = 20, offset = 0) =>
    request('GET', `/timeline/home?limit=${limit}&offset=${offset}`, null, token),
  userTimeline: (userId, limit = 20, offset = 0) =>
    request('GET', `/timeline/user/${userId}?limit=${limit}&offset=${offset}`),
  searchUsers: (query, limit = 20) =>
    request('GET', `/users/search?q=${encodeURIComponent(query)}&limit=${limit}`),
};
