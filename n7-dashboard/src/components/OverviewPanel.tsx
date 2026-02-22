import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  ShieldAlert, Shield, Activity, Database,
  AlertTriangle, CheckCircle, ChevronRight,
} from 'lucide-react';
import { getSeverityColor, formatRelativeTime } from '../utils/alertUtils';
import type { Alert } from '../utils/alertUtils';
import './OverviewPanel.css';

const API_BASE = import.meta.env.VITE_API_URL;

interface Agent {
  id: string;
  status: string;
  agent_type: string;
  agent_subtype: string;
  last_heartbeat: string;
}

interface IOCStats {
  ip?: number;
  domain?: number;
  url?: number;
  hash?: number;
}

interface OverviewPanelProps {
  onNavigate: (tab: 'overview' | 'incidents' | 'events' | 'agents' | 'infrastructure') => void;
}

export function OverviewPanel({ onNavigate }: OverviewPanelProps) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [iocStats, setIocStats] = useState<IOCStats>({});
  const [eventCount, setEventCount] = useState(0);

  const fetchData = useCallback(async () => {
    try {
      const [alertsRes, agentsRes, eventsRes] = await Promise.allSettled([
        axios.get(`${API_BASE}/api/v1/alerts/?limit=50`),
        axios.get(`${API_BASE}/api/v1/agents/`),
        axios.get(`${API_BASE}/api/v1/events/?limit=1`),
      ]);

      if (alertsRes.status === 'fulfilled') setAlerts(alertsRes.value.data);
      if (agentsRes.status === 'fulfilled') setAgents(agentsRes.value.data);
      if (eventsRes.status === 'fulfilled') {
        // The events endpoint returns an array; use length or total from headers
        setEventCount(eventsRes.value.data.length > 0 ? eventsRes.value.data.length : 0);
      }

      // IOC stats — may not be available
      try {
        const iocRes = await axios.get(`${API_BASE}/api/v1/threat-intel/stats`);
        // API returns { status, ioc_counts: { ip, domain, url, hash, other, total } }
        setIocStats(iocRes.data.ioc_counts ?? iocRes.data);
      } catch { /* IOC stats optional */ }
    } catch (err) {
      console.error('Overview fetch failed', err);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Computed metrics
  const activeThreats = alerts.filter(a => a.status === 'new').length;
  const criticalCount = alerts.filter(a => a.severity === 'critical').length;
  const highCount = alerts.filter(a => a.severity === 'high').length;
  const mediumCount = alerts.filter(a => a.severity === 'medium').length;
  const lowCount = alerts.filter(a => a.severity === 'low').length;
  const activeAgents = agents.filter(a => a.status === 'active').length;
  const totalAgents = agents.length;
  const totalIOCs = (iocStats.ip ?? 0) + (iocStats.domain ?? 0) + (iocStats.url ?? 0) + (iocStats.hash ?? 0);

  const recentCritical = alerts
    .filter(a => a.severity === 'critical' || a.severity === 'high')
    .slice(0, 5);

  const staleAgents = agents.filter(a => {
    if (!a.last_heartbeat) return true;
    const hb = new Date(a.last_heartbeat.endsWith('Z') ? a.last_heartbeat : a.last_heartbeat + 'Z');
    return Date.now() - hb.getTime() > 90000;
  });

  // Severity distribution bar
  const totalAlerts = alerts.length || 1;
  const severityPcts = {
    critical: (criticalCount / totalAlerts) * 100,
    high: (highCount / totalAlerts) * 100,
    medium: (mediumCount / totalAlerts) * 100,
    low: (lowCount / totalAlerts) * 100,
  };

  return (
    <div className="overview">
      {/* ── Metric Cards ── */}
      <div className="overview-metrics">
        <div className={`metric-card ${activeThreats > 0 ? 'metric-card--alert' : 'metric-card--ok'}`}>
          <div className="metric-icon-wrap metric-icon--threats">
            <ShieldAlert size={22} />
          </div>
          <div className="metric-info">
            <span className="metric-value">{activeThreats}</span>
            <span className="metric-label">Active Threats</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon-wrap metric-icon--agents">
            <Shield size={22} />
          </div>
          <div className="metric-info">
            <span className="metric-value">
              {activeAgents}<span className="metric-value-sub">/{totalAgents}</span>
            </span>
            <span className="metric-label">Agents Online</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon-wrap metric-icon--events">
            <Activity size={22} />
          </div>
          <div className="metric-info">
            <span className="metric-value">{eventCount > 0 ? eventCount : '--'}</span>
            <span className="metric-label">Recent Events</span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon-wrap metric-icon--ioc">
            <Database size={22} />
          </div>
          <div className="metric-info">
            <span className="metric-value">{totalIOCs > 0 ? totalIOCs : '--'}</span>
            <span className="metric-label">Threat Intel IOCs</span>
          </div>
        </div>
      </div>

      {/* ── Two-column section ── */}
      <div className="overview-grid">
        {/* Recent Critical Alerts */}
        <div className="overview-card">
          <div className="overview-card-header">
            <h2 className="overview-card-title">
              <AlertTriangle size={18} />
              Recent Critical Alerts
            </h2>
            <button
              className="overview-see-all"
              onClick={() => onNavigate('incidents')}
            >
              View All <ChevronRight size={14} />
            </button>
          </div>
          <div className="overview-card-body">
            {recentCritical.length === 0 ? (
              <div className="overview-empty">
                <CheckCircle size={28} />
                <p>No critical threats detected</p>
              </div>
            ) : (
              <div className="critical-list">
                {recentCritical.map(alert => (
                  <button
                    key={alert.alert_id}
                    className="critical-item"
                    onClick={() => onNavigate('incidents')}
                  >
                    <span
                      className="critical-severity-dot"
                      style={{ background: getSeverityColor(alert.severity) }}
                    />
                    <div className="critical-info">
                      <span className="critical-rule">
                        {alert.reasoning?.rule ?? 'Unknown Rule'}
                      </span>
                      <span className="critical-meta">
                        Score: {alert.threat_score} &middot; {formatRelativeTime(alert.created_at)}
                      </span>
                    </div>
                    <span className="critical-score">{alert.threat_score}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Agent Health */}
        <div className="overview-card">
          <div className="overview-card-header">
            <h2 className="overview-card-title">
              <Shield size={18} />
              Agent Health
            </h2>
          </div>
          <div className="overview-card-body">
            <div className="agent-health-summary">
              <div className="agent-health-ring">
                <svg viewBox="0 0 100 100" className="health-ring-svg">
                  <circle cx="50" cy="50" r="40" fill="none" stroke="var(--border-color)" strokeWidth="8" />
                  <circle
                    cx="50" cy="50" r="40"
                    fill="none"
                    stroke="var(--accent-success)"
                    strokeWidth="8"
                    strokeDasharray={`${totalAgents > 0 ? (activeAgents / totalAgents) * 251.2 : 0} 251.2`}
                    strokeLinecap="round"
                    transform="rotate(-90 50 50)"
                  />
                </svg>
                <div className="health-ring-label">
                  <span className="health-ring-value">{totalAgents > 0 ? Math.round((activeAgents / totalAgents) * 100) : 0}%</span>
                  <span className="health-ring-sub">Healthy</span>
                </div>
              </div>
              <div className="agent-health-stats">
                <div className="health-stat">
                  <span className="health-stat-dot health-stat-dot--active" />
                  <span className="health-stat-label">Active</span>
                  <span className="health-stat-value">{activeAgents}</span>
                </div>
                <div className="health-stat">
                  <span className="health-stat-dot health-stat-dot--stale" />
                  <span className="health-stat-label">Stale / Offline</span>
                  <span className="health-stat-value">{staleAgents.length}</span>
                </div>
              </div>
            </div>
            {staleAgents.length > 0 && (
              <div className="stale-agents">
                <span className="stale-agents-heading">Stale Agents</span>
                {staleAgents.slice(0, 3).map(agent => (
                  <div key={agent.id} className="stale-agent-row">
                    <span className="stale-agent-id">{agent.id.slice(0, 8)}...</span>
                    <span className="stale-agent-type">{agent.agent_type}</span>
                    <span className="stale-agent-hb">{formatRelativeTime(agent.last_heartbeat)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Severity Distribution ── */}
      <div className="overview-card overview-card--full">
        <div className="overview-card-header">
          <h2 className="overview-card-title">
            <Activity size={18} />
            Alert Severity Distribution
          </h2>
          <span className="overview-card-subtitle">{alerts.length} total alerts</span>
        </div>
        <div className="overview-card-body">
          <div className="severity-bar-container">
            <div className="severity-bar">
              {criticalCount > 0 && (
                <div className="severity-segment severity-segment--critical" style={{ width: `${severityPcts.critical}%` }} title={`Critical: ${criticalCount}`} />
              )}
              {highCount > 0 && (
                <div className="severity-segment severity-segment--high" style={{ width: `${severityPcts.high}%` }} title={`High: ${highCount}`} />
              )}
              {mediumCount > 0 && (
                <div className="severity-segment severity-segment--medium" style={{ width: `${severityPcts.medium}%` }} title={`Medium: ${mediumCount}`} />
              )}
              {lowCount > 0 && (
                <div className="severity-segment severity-segment--low" style={{ width: `${severityPcts.low}%` }} title={`Low: ${lowCount}`} />
              )}
              {alerts.length === 0 && (
                <div className="severity-segment severity-segment--empty" style={{ width: '100%' }} />
              )}
            </div>
            <div className="severity-legend">
              <div className="legend-item">
                <span className="legend-dot legend-dot--critical" />
                <span>Critical ({criticalCount})</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot legend-dot--high" />
                <span>High ({highCount})</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot legend-dot--medium" />
                <span>Medium ({mediumCount})</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot legend-dot--low" />
                <span>Low ({lowCount})</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
