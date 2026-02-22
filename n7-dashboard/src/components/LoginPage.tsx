import { useState } from 'react';
import type { FormEvent } from 'react';
import axios from 'axios';
import { Shield } from 'lucide-react';
import './LoginPage.css';

const API_BASE = import.meta.env.VITE_API_URL;

interface LoginPageProps {
  onLogin: (token: string) => void;
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // FastAPI OAuth2PasswordRequestForm expects form-encoded body
      const params = new URLSearchParams();
      params.append('username', username);
      params.append('password', password);

      const response = await axios.post(`${API_BASE}/api/v1/token`, params, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });

      const token: string = response.data.access_token;
      localStorage.setItem('n7_token', token);
      onLogin(token);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(detail || 'Invalid username or password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <Shield size={32} className="login-icon" />
          <h1 className="login-title">NAGA-7</h1>
          <p className="login-subtitle">Security Monitoring Platform</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          {error && <div className="login-error">{error}</div>}

          <div className="login-field">
            <label className="login-label" htmlFor="username">Username</label>
            <input
              id="username"
              className="login-input"
              type="text"
              autoComplete="username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              disabled={loading}
            />
          </div>

          <div className="login-field">
            <label className="login-label" htmlFor="password">Password</label>
            <input
              id="password"
              className="login-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              disabled={loading}
            />
          </div>

          <button className="login-btn" type="submit" disabled={loading}>
            {loading ? 'Authenticating…' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
}
