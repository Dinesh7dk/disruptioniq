/**
 * frontend/src/api.js
 * In-memory JWT token and user session store.
 * The token is stored purely in JavaScript memory (never in localStorage or cookies).
 */
let inMemoryToken = null;
let inMemoryUser = null;

export const setAuth = (token, user) => {
  inMemoryToken = token;
  inMemoryUser = user;
};

export const clearAuth = () => {
  inMemoryToken = null;
  inMemoryUser = null;
};

export const getToken = () => inMemoryToken;
export const getUser = () => inMemoryUser;

const API_BASE = 'http://127.0.0.1:8000';

export const apiFetch = async (endpoint, options = {}) => {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
  
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  };

  if (inMemoryToken) {
    headers['Authorization'] = `Bearer ${inMemoryToken}`;
  }

  const response = await fetch(url, { ...options, headers });
  
  if (response.status === 401) {
    clearAuth();
    window.dispatchEvent(new CustomEvent('auth-expired'));
  }
  
  return response;
};
