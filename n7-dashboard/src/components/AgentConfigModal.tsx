import { useState, useEffect } from 'react';
import axios from 'axios';
import { Settings, X } from 'lucide-react';
import './AgentConfigModal.css';

// Shared fields
interface BaseConfig {
  agent_id: string;
  agent_type: string;
  config_version: number;
  zone: string;
  log_level: string;
  environment: string;
}

interface SentinelConfig extends BaseConfig {
  probe_interval_seconds: number | null;
  detection_thresholds: Record<string, number>;
  enabled_probes: string[];
}

interface StrikerConfig extends BaseConfig {
  capabilities: string[];
  allowed_actions: string[] | null;
  action_defaults: Record<string, Record<string, unknown>>;
  max_concurrent_actions: number | null;
}

type AgentConfig = SentinelConfig | StrikerConfig;

interface AgentConfigModalProps {
  agentId: string;
  agentType: string;
  onClose: () => void;
  onAuthError?: () => void;
}

const API_BASE = import.meta.env.VITE_API_URL;

function getAuthHeaders() {
  const token = localStorage.getItem('n7_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const SENTINEL_PROBES = ['system', 'network', 'process', 'file'];
const STRIKER_ACTIONS = ['network_block', 'network_unblock', 'process_kill', 'isolate_host', 'unisolate_host', 'file_quarantine'];

export function AgentConfigModal({ agentId, agentType, onClose, onAuthError }: AgentConfigModalProps) {
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Shared fields
  const [zone, setZone] = useState('');
  const [logLevel, setLogLevel] = useState('INFO');

  // Sentinel-specific
  const [probeInterval, setProbeInterval] = useState<string>('10');
  const [thresholdsStr, setThresholdsStr] = useState('{}');
  const [enabledProbes, setEnabledProbes] = useState<string[]>([]);

  // Striker-specific
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [allowedActions, setAllowedActions] = useState<string[] | null>(null);
  const [actionDefaultsStr, setActionDefaultsStr] = useState('{}');
  const [maxConcurrent, setMaxConcurrent] = useState<string>('');

  const isSentinel = agentType === 'sentinel';
  const isStriker = agentType === 'striker';

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await axios.get(
          `${API_BASE}/api/v1/agents/${agentId}/config`,
          { headers: getAuthHeaders() }
        );
        const cfg = response.data;
        setConfig(cfg);
        setZone(cfg.zone || '');
        setLogLevel(cfg.log_level || 'INFO');

        if (cfg.agent_type === 'sentinel') {
          const s = cfg as SentinelConfig;
          setProbeInterval(s.probe_interval_seconds != null ? String(s.probe_interval_seconds) : '10');
          setThresholdsStr(JSON.stringify(s.detection_thresholds || {}, null, 2));
          setEnabledProbes(s.enabled_probes || []);
        } else if (cfg.agent_type === 'striker') {
          const k = cfg as StrikerConfig;
          setCapabilities(k.capabilities || []);
          setAllowedActions(k.allowed_actions ?? null);
          setActionDefaultsStr(JSON.stringify(k.action_defaults || {}, null, 2));
          setMaxConcurrent(k.max_concurrent_actions != null ? String(k.max_concurrent_actions) : '');
        }
      } catch (err: any) {
        if (err?.response?.status === 401) {
          onAuthError?.();
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

    const payload: Record<string, unknown> = {};
    if (zone) payload.zone = zone;
    if (logLevel) payload.log_level = logLevel;

    if (isSentinel) {
      let parsedThresholds: Record<string, number> = {};
      try {
        parsedThresholds = JSON.parse(thresholdsStr);
      } catch {
        setError('Detection thresholds must be valid JSON.');
        setSaving(false);
        return;
      }
      if (probeInterval !== '') payload.probe_interval_seconds = parseInt(probeInterval, 10);
      payload.detection_thresholds = parsedThresholds;
      payload.enabled_probes = enabledProbes;
    }

    if (isStriker) {
      let parsedDefaults: Record<string, unknown> = {};
      try {
        parsedDefaults = JSON.parse(actionDefaultsStr);
      } catch {
        setError('Action defaults must be valid JSON.');
        setSaving(false);
        return;
      }
      payload.capabilities = capabilities;
      payload.allowed_actions = allowedActions;
      payload.action_defaults = parsedDefaults;
      if (maxConcurrent !== '') payload.max_concurrent_actions = parseInt(maxConcurrent, 10);
    }

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
      if (err?.response?.status === 401) {
        onAuthError?.();
      } else {
        const detail = err?.response?.data?.detail;
        setError(detail || 'Failed to update configuration.');
      }
    } finally {
      setSaving(false);
    }
  };

  const toggleProbe = (probe: string) => {
    setEnabledProbes(prev =>
      prev.includes(probe) ? prev.filter(p => p !== probe) : [...prev, probe]
    );
  };

  const toggleCapability = (action: string) => {
    setCapabilities(prev =>
      prev.includes(action) ? prev.filter(a => a !== action) : [...prev, action]
    );
  };

  const toggleAllowedAction = (action: string) => {
    setAllowedActions(prev => {
      const current = prev ?? [...capabilities];
      return current.includes(action)
        ? current.filter(a => a !== action)
        : [...current, action];
    });
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
            <span className={`acm-agent-type acm-agent-type--${agentType}`}>{agentType}</span>
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
                {config.config_version === 0 && (
                  <span className="acm-version-hint"> — first save will provision this agent</span>
                )}
              </div>

              {/* ── Shared fields ── */}
              <div className="acm-section-label">General</div>

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

              {/* ── Sentinel-specific fields ── */}
              {isSentinel && (
                <>
                  <div className="acm-section-label">Monitoring</div>

                  <div className="acm-field">
                    <label className="acm-label">Probe Interval (seconds)</label>
                    <input
                      className="acm-input"
                      type="number"
                      min={1}
                      max={300}
                      value={probeInterval}
                      onChange={e => setProbeInterval(e.target.value)}
                      placeholder="e.g. 10"
                    />
                  </div>

                  <div className="acm-field">
                    <label className="acm-label">Enabled Probes</label>
                    <div className="acm-checkbox-group">
                      {SENTINEL_PROBES.map(probe => (
                        <label key={probe} className="acm-checkbox-label">
                          <input
                            type="checkbox"
                            checked={enabledProbes.includes(probe)}
                            onChange={() => toggleProbe(probe)}
                          />
                          {probe}
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="acm-field">
                    <label className="acm-label">Detection Thresholds (JSON)</label>
                    <div className="acm-field-hint">
                      Keys: cpu_threshold, mem_threshold, disk_threshold, load_multiplier
                    </div>
                    <textarea
                      className="acm-textarea"
                      value={thresholdsStr}
                      onChange={e => setThresholdsStr(e.target.value)}
                      rows={5}
                      placeholder='{"cpu_threshold": 80, "mem_threshold": 85, "disk_threshold": 90, "load_multiplier": 2.0}'
                    />
                  </div>
                </>
              )}

              {/* ── Striker-specific fields ── */}
              {isStriker && (
                <>
                  <div className="acm-section-label">Response Actions</div>

                  <div className="acm-field">
                    <label className="acm-label">Capabilities</label>
                    <div className="acm-field-hint">Action types this striker is provisioned to execute.</div>
                    <div className="acm-checkbox-group">
                      {STRIKER_ACTIONS.map(action => (
                        <label key={action} className="acm-checkbox-label">
                          <input
                            type="checkbox"
                            checked={capabilities.includes(action)}
                            onChange={() => toggleCapability(action)}
                          />
                          {action}
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="acm-field">
                    <label className="acm-label">Allowed Actions</label>
                    <div className="acm-field-hint">
                      Restrict which capabilities can be dispatched at runtime.
                      Leave all unchecked to allow all capabilities.
                    </div>
                    <div className="acm-checkbox-group">
                      {capabilities.map(action => (
                        <label key={action} className="acm-checkbox-label">
                          <input
                            type="checkbox"
                            checked={allowedActions === null || allowedActions.includes(action)}
                            onChange={() => toggleAllowedAction(action)}
                          />
                          {action}
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="acm-field">
                    <label className="acm-label">Action Defaults (JSON)</label>
                    <div className="acm-field-hint">
                      Default params merged into each action command. Command params take precedence.
                    </div>
                    <textarea
                      className="acm-textarea"
                      value={actionDefaultsStr}
                      onChange={e => setActionDefaultsStr(e.target.value)}
                      rows={4}
                      placeholder='{"network_block": {"duration": 3600}}'
                    />
                  </div>

                  <div className="acm-field">
                    <label className="acm-label">Max Concurrent Actions</label>
                    <input
                      className="acm-input"
                      type="number"
                      min={1}
                      value={maxConcurrent}
                      onChange={e => setMaxConcurrent(e.target.value)}
                      placeholder="Leave empty for unlimited"
                    />
                  </div>
                </>
              )}
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
