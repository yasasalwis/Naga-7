import { useState, useEffect } from 'react';
import axios from 'axios';
import { Edit, X } from 'lucide-react';
import './NodeEditModal.css';

interface InfraNode {
  id: string;
  hostname: string | null;
  ip_address: string;
  os_type: string | null;
  ssh_port: number;
  winrm_port: number;
  ssh_username: string | null;
  deployed_agent_id: string | null;
  deployed_agent_type: string | null;
}

interface AgentConfig {
  agent_id: string;
  config_version: number;
  zone: string;
  log_level: string;
  probe_interval_seconds: number | null;
  detection_thresholds: Record<string, number>;
  capabilities: string[];
}

interface NodeEditModalProps {
  node: InfraNode;
  onClose: () => void;
  onSaved: () => void;
  onAuthError?: () => void;
}

const API_BASE = `${import.meta.env.VITE_API_URL}/api/v1`;

function getAuthHeaders() {
  const token = localStorage.getItem('n7_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function NodeEditModal({ node, onClose, onSaved, onAuthError }: NodeEditModalProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Section A — Node registry fields
  const [hostname, setHostname] = useState(node.hostname ?? '');
  const [osType, setOsType] = useState<string>(node.os_type ?? 'unknown');
  const [sshPort, setSshPort] = useState(String(node.ssh_port));
  const [winrmPort, setWinrmPort] = useState(String(node.winrm_port));
  const [sshUsername, setSshUsername] = useState(node.ssh_username ?? '');
  const [sshPassword, setSshPassword] = useState('');
  const [sshKeyPath, setSshKeyPath] = useState('');

  // Section B — Agent config (only if agent deployed)
  const [agentConfigVersion, setAgentConfigVersion] = useState<number | null>(null);
  const [agentZone, setAgentZone] = useState('');
  const [agentSubtype, setAgentSubtype] = useState('');
  const [agentLogLevel, setAgentLogLevel] = useState('INFO');
  const [agentProbeInterval, setAgentProbeInterval] = useState('');
  const [agentCapabilities, setAgentCapabilities] = useState('');
  const [agentThresholds, setAgentThresholds] = useState('{}');
  const [agentConfigLoading, setAgentConfigLoading] = useState(false);
  const [agentConfigError, setAgentConfigError] = useState<string | null>(null);

  const hasAgent = !!node.deployed_agent_id;

  // Pre-fill agent config if an agent is deployed
  useEffect(() => {
    if (!hasAgent) return;
    setAgentConfigLoading(true);
    axios
      .get(`${API_BASE}/agents/${node.deployed_agent_id}/config`, {
        headers: getAuthHeaders(),
      })
      .then(res => {
        const cfg: AgentConfig = res.data;
        setAgentConfigVersion(cfg.config_version);
        setAgentZone(cfg.zone ?? '');
        setAgentLogLevel(cfg.log_level ?? 'INFO');
        setAgentProbeInterval(
          cfg.probe_interval_seconds != null ? String(cfg.probe_interval_seconds) : ''
        );
        setAgentCapabilities((cfg.capabilities ?? []).join(', '));
        setAgentThresholds(JSON.stringify(cfg.detection_thresholds ?? {}, null, 2));
      })
      .catch(err => {
        if (err?.response?.status === 404) {
          setAgentConfigError('Agent config not provisioned yet.');
        } else {
          setAgentConfigError('Failed to load agent configuration.');
        }
      })
      .finally(() => setAgentConfigLoading(false));
  }, [node.deployed_agent_id, hasAgent]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccessMsg(null);

    // Validate agent thresholds JSON before any network calls
    let parsedThresholds: Record<string, number> = {};
    if (hasAgent && !agentConfigError) {
      try {
        parsedThresholds = JSON.parse(agentThresholds);
      } catch {
        setError('Detection thresholds must be valid JSON.');
        setSaving(false);
        return;
      }
    }

    try {
      // Section A: Update node registry
      const nodePayload: Record<string, unknown> = {};
      if (hostname !== (node.hostname ?? '')) nodePayload.hostname = hostname || null;
      if (osType !== (node.os_type ?? 'unknown')) nodePayload.os_type = osType;
      if (sshPort !== String(node.ssh_port)) nodePayload.ssh_port = parseInt(sshPort, 10);
      if (winrmPort !== String(node.winrm_port)) nodePayload.winrm_port = parseInt(winrmPort, 10);
      if (sshUsername !== (node.ssh_username ?? '')) nodePayload.ssh_username = sshUsername || null;
      if (sshPassword) nodePayload.ssh_password = sshPassword;
      if (sshKeyPath) nodePayload.ssh_key_path = sshKeyPath;

      if (Object.keys(nodePayload).length > 0) {
        await axios.put(
          `${API_BASE}/deployment/nodes/${node.id}`,
          nodePayload,
          { headers: getAuthHeaders() }
        );
      }

      // Section B: Update agent config (if deployed and config loaded)
      if (hasAgent && !agentConfigError && node.deployed_agent_id) {
        const agentPayload: Record<string, unknown> = {};
        if (agentSubtype) agentPayload.agent_subtype = agentSubtype;
        if (agentZone) agentPayload.zone = agentZone;
        const caps = agentCapabilities
          .split(',')
          .map(s => s.trim())
          .filter(Boolean);
        if (caps.length > 0) agentPayload.capabilities = caps;
        if (agentProbeInterval !== '')
          agentPayload.probe_interval_seconds = parseInt(agentProbeInterval, 10);
        agentPayload.detection_thresholds = parsedThresholds;
        agentPayload.log_level = agentLogLevel;

        await axios.put(
          `${API_BASE}/agents/${node.deployed_agent_id}`,
          agentPayload,
          { headers: getAuthHeaders() }
        );
      }

      setSuccessMsg('Node updated successfully. Agent will reload within ~60 seconds.');
      onSaved();
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        if (err.response?.status === 401) {
          onAuthError?.();
        } else {
          setError(err.response?.data?.detail ?? err.message);
        }
      } else {
        setError('Save failed. Please try again.');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="nem-overlay" onClick={onClose}>
      <div className="nem-modal" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="nem-header">
          <div className="nem-title">
            <Edit size={18} className="nem-icon" />
            <span>Edit Node</span>
          </div>
          <div className="nem-subtitle">
            <span className="nem-ip">{node.ip_address}</span>
            {node.deployed_agent_type && (
              <span className="nem-agent-pill">{node.deployed_agent_type}</span>
            )}
          </div>
          <button className="nem-close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="nem-body">
          {error && <div className="nem-error">{error}</div>}
          {successMsg && <div className="nem-success">{successMsg}</div>}

          {/* ── Section A: Node Registry ── */}
          <p className="nem-section-label">Node Registry</p>

          <div className="nem-field-row">
            <div className="nem-field">
              <label className="nem-label">Hostname</label>
              <input
                className="nem-input"
                value={hostname}
                onChange={e => setHostname(e.target.value)}
                placeholder="e.g. server-01.local"
              />
            </div>
            <div className="nem-field">
              <label className="nem-label">OS Type</label>
              <select
                className="nem-select"
                value={osType}
                onChange={e => setOsType(e.target.value)}
              >
                <option value="linux">Linux</option>
                <option value="macos">macOS</option>
                <option value="windows">Windows</option>
                <option value="unknown">Unknown</option>
              </select>
            </div>
          </div>

          <div className="nem-field-row">
            <div className="nem-field">
              <label className="nem-label">SSH Port</label>
              <input
                className="nem-input nem-input--port"
                type="number"
                value={sshPort}
                onChange={e => setSshPort(e.target.value)}
                min={1}
                max={65535}
              />
            </div>
            <div className="nem-field">
              <label className="nem-label">WinRM Port</label>
              <input
                className="nem-input nem-input--port"
                type="number"
                value={winrmPort}
                onChange={e => setWinrmPort(e.target.value)}
                min={1}
                max={65535}
              />
            </div>
          </div>

          <div className="nem-divider" />
          <p className="nem-section-label">SSH Credentials (leave blank to keep current)</p>

          <div className="nem-field">
            <label className="nem-label">Username</label>
            <input
              className="nem-input"
              value={sshUsername}
              onChange={e => setSshUsername(e.target.value)}
              placeholder="e.g. ubuntu"
              autoComplete="username"
            />
          </div>

          <div className="nem-field-row">
            <div className="nem-field">
              <label className="nem-label">Password</label>
              <input
                className="nem-input"
                type="password"
                value={sshPassword}
                onChange={e => setSshPassword(e.target.value)}
                placeholder="leave blank to keep current"
                autoComplete="new-password"
              />
            </div>
            <div className="nem-field">
              <label className="nem-label">SSH Key Path</label>
              <input
                className="nem-input"
                value={sshKeyPath}
                onChange={e => setSshKeyPath(e.target.value)}
                placeholder="e.g. /root/.ssh/id_rsa"
              />
            </div>
          </div>

          {/* ── Section B: Agent Config (if deployed) ── */}
          {hasAgent && (
            <>
              <div className="nem-divider" />
              <p className="nem-section-label">
                Agent Configuration
                {agentConfigVersion != null && (
                  <span className="nem-config-version"> — v{agentConfigVersion}</span>
                )}
              </p>

              {agentConfigLoading && (
                <p className="nem-loading">Loading agent configuration…</p>
              )}

              {agentConfigError && !agentConfigLoading && (
                <div className="nem-agent-config-error">{agentConfigError}</div>
              )}

              {!agentConfigLoading && !agentConfigError && (
                <>
                  <div className="nem-field-row">
                    <div className="nem-field">
                      <label className="nem-label">Zone</label>
                      <input
                        className="nem-input"
                        value={agentZone}
                        onChange={e => setAgentZone(e.target.value)}
                        placeholder="e.g. default, dmz, production"
                      />
                    </div>
                    <div className="nem-field">
                      <label className="nem-label">Subtype</label>
                      <input
                        className="nem-input"
                        value={agentSubtype}
                        onChange={e => setAgentSubtype(e.target.value)}
                        placeholder="e.g. system, network"
                      />
                    </div>
                  </div>

                  <div className="nem-field-row">
                    <div className="nem-field">
                      <label className="nem-label">Log Level</label>
                      <select
                        className="nem-select"
                        value={agentLogLevel}
                        onChange={e => setAgentLogLevel(e.target.value)}
                      >
                        <option value="DEBUG">DEBUG</option>
                        <option value="INFO">INFO</option>
                        <option value="WARNING">WARNING</option>
                        <option value="ERROR">ERROR</option>
                      </select>
                    </div>
                    <div className="nem-field">
                      <label className="nem-label">Probe Interval (s)</label>
                      <input
                        className="nem-input nem-input--port"
                        type="number"
                        min={1}
                        max={300}
                        value={agentProbeInterval}
                        onChange={e => setAgentProbeInterval(e.target.value)}
                        placeholder="e.g. 5"
                      />
                    </div>
                  </div>

                  <div className="nem-field">
                    <label className="nem-label">Capabilities (comma-separated)</label>
                    <input
                      className="nem-input"
                      value={agentCapabilities}
                      onChange={e => setAgentCapabilities(e.target.value)}
                      placeholder="e.g. system_probe, file_integrity, network_monitor"
                    />
                  </div>

                  <div className="nem-field">
                    <label className="nem-label">Detection Thresholds (JSON)</label>
                    <textarea
                      className="nem-textarea"
                      value={agentThresholds}
                      onChange={e => setAgentThresholds(e.target.value)}
                      rows={3}
                      placeholder='{"cpu_threshold": 90, "failed_login_threshold": 5}'
                    />
                  </div>
                </>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="nem-footer">
          <button className="nem-btn nem-btn--secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="nem-btn nem-btn--primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
