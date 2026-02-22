import { useState } from 'react';
import './App.css';
import { LoginPage } from './components/LoginPage';
import { OverviewPanel } from './components/OverviewPanel';
import { IncidentPanel } from './components/IncidentPanel';
import { EventStream } from './components/EventStream';
import { AgentList } from './components/AgentList';
import { NodeDeployment } from './components/NodeDeployment';
import {
  LayoutDashboard, Brain, Activity, Shield, Server,
  LogOut, PanelLeftClose, PanelLeft, Zap,
} from 'lucide-react';

type TabId = 'overview' | 'incidents' | 'events' | 'agents' | 'infrastructure';

interface TabDef {
  id: TabId;
  label: string;
  icon: typeof LayoutDashboard;
}

const tabs: TabDef[] = [
  { id: 'overview',       label: 'Overview',        icon: LayoutDashboard },
  { id: 'incidents',      label: 'Incidents',       icon: Brain },
  { id: 'events',         label: 'Events',          icon: Activity },
  { id: 'agents',         label: 'Agents',          icon: Shield },
  { id: 'infrastructure', label: 'Infrastructure',  icon: Server },
];

function App() {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem('n7_token')
  );
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

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

  const currentTab = tabs.find(t => t.id === activeTab)!;

  const renderContent = () => {
    switch (activeTab) {
      case 'overview':
        return <OverviewPanel onNavigate={setActiveTab} />;
      case 'incidents':
        return <IncidentPanel />;
      case 'events':
        return <EventStream />;
      case 'agents':
        return <AgentList onAuthError={handleLogout} />;
      case 'infrastructure':
        return <NodeDeployment onAuthError={handleLogout} />;
    }
  };

  return (
    <div className="app-layout">
      {/* ── Sidebar ── */}
      <aside className={`sidebar ${sidebarCollapsed ? 'sidebar--collapsed' : ''}`}>
        {/* Brand */}
        <div className="sidebar-brand">
          <Zap className="sidebar-brand-icon" size={24} />
          {!sidebarCollapsed && (
            <div className="sidebar-brand-text">
              <span className="sidebar-brand-name">NAGA-7</span>
              <span className="sidebar-brand-sub">Security Platform</span>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="sidebar-nav">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                className={`sidebar-nav-item ${isActive ? 'sidebar-nav-item--active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
                title={sidebarCollapsed ? tab.label : undefined}
              >
                <Icon size={20} className="sidebar-nav-icon" />
                {!sidebarCollapsed && (
                  <span className="sidebar-nav-label">{tab.label}</span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Collapse toggle */}
        <div className="sidebar-footer">
          <button
            className="sidebar-collapse-btn"
            onClick={() => setSidebarCollapsed(prev => !prev)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {sidebarCollapsed
              ? <PanelLeft size={18} />
              : <PanelLeftClose size={18} />
            }
            {!sidebarCollapsed && <span>Collapse</span>}
          </button>
        </div>
      </aside>

      {/* ── Main Content ── */}
      <div className={`content-area ${sidebarCollapsed ? 'content-area--expanded' : ''}`}>
        {/* Top bar */}
        <header className="topbar">
          <div className="topbar-left">
            <h1 className="topbar-title">{currentTab.label}</h1>
          </div>
          <div className="topbar-right">
            <button className="topbar-logout" onClick={handleLogout} title="Sign out">
              <LogOut size={16} />
              <span>Sign out</span>
            </button>
          </div>
        </header>

        {/* Tab content */}
        <main className="tab-content">
          {renderContent()}
        </main>
      </div>
    </div>
  );
}

export default App;
