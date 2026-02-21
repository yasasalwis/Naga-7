import { useState } from 'react';
import './App.css';
import { AgentList } from './components/AgentList';
import { AlertPanel } from './components/AlertPanel';
import { EventStream } from './components/EventStream';
import { NodeDeployment } from './components/NodeDeployment';
import { LoginPage } from './components/LoginPage';
import { Shield, LogOut } from 'lucide-react';

function App() {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem('n7_token')
  );

  const handleLogin = (newToken: string) => {
    setToken(newToken);
  };

  const handleLogout = () => {
    localStorage.removeItem('n7_token');
    setToken(null);
  };

  if (!token) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-content">
          <Shield className="header-icon" />
          <div className="header-title">
            <h1>NAGA-7 Dashboard</h1>
            <p>Security Event Monitoring System</p>
          </div>
          <button className="logout-btn" onClick={handleLogout} title="Sign out">
            <LogOut size={16} />
            <span>Sign out</span>
          </button>
        </div>
      </header>

      <main className="main-content">
        <div className="dashboard-grid">
          <div className="grid-item">
            <AgentList onAuthError={handleLogout} />
          </div>
          <div className="grid-item">
            <EventStream />
          </div>
          <div className="grid-item grid-item--full">
            <AlertPanel />
          </div>
          <div className="grid-item grid-item--full">
            <NodeDeployment onAuthError={handleLogout} />
          </div>
        </div>
      </main>

      <footer className="app-footer">
        <div className="footer-content">
          NAGA-7 Security Monitoring Platform v0.2.0
        </div>
      </footer>
    </div>
  );
}

export default App;
