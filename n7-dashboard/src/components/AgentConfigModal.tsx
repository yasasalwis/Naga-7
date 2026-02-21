import { useState, useEffect } from 'react';
import axios from 'axios';
import { Settings, X } from 'lucide-react';
import './AgentConfigModal.css';

interface AgentConfig {
  agent_id: string;
  config_version: number;
  zone: string;
  log_level: string;
  probe_interval_seconds: number | null;
  detection_thresholds: Record<string, number>;
  capabilities: string[];
  environment: string;
}

interface AgentConfigModalProps {
  agentId: string;
  agentType: string;
  onClose: () => void;
}

const API_BASE = import.meta.env.VITE_API_URL;

function getAuthHeaders() {
  const token = localStorage.getItem('n7_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function AgentConfigModal({ agentId, agentType, onClose }: AgentConfigModalProps) {
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form fields
  const [zone, setZone] = useState('');
  const [logLevel, setLogLevel] = useState('INFO');
  const [probeInterval, setProbeInterval] = useState<string>('');
  const [capabilitiesStr, setCapabilitiesStr] = useState('');
  const [thresholdsStr, setThresholdsStr] = useState('{}');

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await axios.get(
          `${API_BASE}/api/v1/agents/${agentId}/config`,
          { headers: getAuthHeaders() }
        );
        const cfg: AgentConfig = response.data;
        setConfig(cfg);
        setZone(cfg.zone || '');
        setLogLevel(cfg.log_level || 'INFO');
        setProbeInterval(cfg.probe_interval_seconds != null ? String(cfg.probe_interval_seconds) : '');
        setCapabilitiesStr((cfg.capabilities || []).join(', '));
        setThresholdsStr(JSON.stringify(cfg.detection_thresholds || {}, null, 2));
      } catch (err: any) {
        if (err?.response?.status === 404) {
          setError('No configuration provisioned for this agent yet. Deploy the agent first.');
        } else {
          setError('Failed to load agent configuration.');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, [agentId]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccessMsg(null);

    let parsedThresholds: Record<string, number> = {};
    try {
      parsedThresholds = JSON.parse(thresholdsStr);
    } catch {
      setError('Detection thresholds must be valid JSON.');
      setSaving(false);
      return;
    }

    const capabilities = capabilitiesStr
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);

    const payload: Record<string, unknown> = {};
    if (zone) payload.zone = zone;
    if (logLevel) payload.log_level = logLevel;
    if (probeInterval !== '') payload.probe_interval_seconds = parseInt(probeInterval, 10);
    if (capabilities.length > 0) payload.capabilities = capabilities;
    payload.detection_thresholds = parsedThresholds;

    try {
      const response = await axios.put(
        `${API_BASE}/api/v1/agents/${agentId}/config`,
        payload,
        { headers: getAuthHeaders() }
      );
      setSuccessMsg(
        `Config updated to version ${response.data.config_version}. ` +
        'Agent will reload within ~60 seconds.'
      );
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(detail || 'Failed to update configuration.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="acm-overlay" onClick={onClose}>
      <div className="acm-modal" onClick={e => e.stopPropagation()}>
        <div className="acm-header">
          <div className="acm-title">
            <Settings size={18} className="acm-icon" />
            <span>Configure Agent</span>
          </div>
          <div className="acm-subtitle">
            <span className="acm-agent-id">{agentId}</span>
            <span className="acm-agent-type">{agentType}</span>
          </div>
          <button className="acm-close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="acm-body">
          {loading && <p className="acm-loading">Loading configuration…</p>}

          {error && !loading && <div className="acm-error">{error}</div>}

          {successMsg && <div className="acm-success">{successMsg}</div>}

          {config && !loading && (
            <>
              <div className="acm-version">
                Config version: <strong>{config.config_version}</strong>
              </div>

              <div className="acm-field">
                <label className="acm-label">Zone</label>
                <input
                  className="acm-input"
                  type="text"
                  value={zone}
                  onChange={e => setZone(e.target.value)}
                  placeholder="e.g. default, dmz, production"
                />
              </div>

              <div className="acm-field">
                <label className="acm-label">Log Level</label>
                <select
                  className="acm-select"
                  value={logLevel}
                  onChange={e => setLogLevel(e.target.value)}
                >
                  <option value="DEBUG">DEBUG</option>
                  <option value="INFO">INFO</option>
                  <option value="WARNING">WARNING</option>
                  <option value="ERROR">ERROR</option>
                </select>
              </div>

              <div className="acm-field">
                <label className="acm-label">Probe Interval (seconds)</label>
                <input
                  className="acm-input"
                  type="number"
                  min={1}
                  max={300}
                  value={probeInterval}
                  onChange={e => setProbeInterval(e.target.value)}
                  placeholder="e.g. 5"
                />
              </div>

              <div className="acm-field">
                <label className="acm-label">Capabilities (comma-separated)</label>
                <input
                  className="acm-input"
                  type="text"
                  value={capabilitiesStr}
                  onChange={e => setCapabilitiesStr(e.target.value)}
                  placeholder="e.g. system_probe, file_integrity, network_monitor"
                />
              </div>

              <div className="acm-field">
                <label className="acm-label">Detection Thresholds (JSON)</label>
                <textarea
                  className="acm-textarea"
                  value={thresholdsStr}
                  onChange={e => setThresholdsStr(e.target.value)}
                  rows={4}
                  placeholder='{"cpu_threshold": 90, "failed_login_threshold": 5}'
                />
              </div>
            </>
          )}
        </div>

        {config && !loading && (
          <div className="acm-footer">
            <button className="acm-btn acm-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              className="acm-btn acm-btn--primary"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Saving…' : 'Save Configuration'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
