import './App.css';
import { AgentList } from './components/AgentList';
import { AlertPanel } from './components/AlertPanel';
import { EventStream } from './components/EventStream';
import { NodeDeployment } from './components/NodeDeployment';
import { Shield } from 'lucide-react';

function App() {
  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-content">
          <Shield className="header-icon" />
          <div className="header-title">
            <h1>NAGA-7 Dashboard</h1>
            <p>Security Event Monitoring System</p>
          </div>
        </div>
      </header>

      <main className="main-content">
        <div className="dashboard-grid">
          <div className="grid-item">
            <AgentList />
          </div>
          <div className="grid-item">
            <EventStream />
          </div>
          <div className="grid-item grid-item--full">
            <AlertPanel />
          </div>
          <div className="grid-item grid-item--full">
            <NodeDeployment />
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
