import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { NodeEditModal } from './NodeEditModal';
import { Server } from 'lucide-react';
import './NodeDeployment.css';

const API_BASE = `${import.meta.env.VITE_API_URL}/api/v1`;

interface InfraNode {
  id: string;
  hostname: string | null;
  ip_address: string;
  mac_address: string | null;
  os_type: string | null;
  ssh_port: number;
  winrm_port: number;
  ssh_username: string | null;
  status: string;
  deployment_status: string;
  deployed_agent_type: string | null;
  deployed_agent_id: string | null;
  error_message: string | null;
  last_seen: string | null;
  discovery_method: string;
}

const defaultDeployConfig = {
  agent_type: 'sentinel' as 'sentinel' | 'striker',
  agent_subtype: 'system',
  zone: 'default',
  ssh_username: '',
  ssh_password: '',
  core_api_url: `${import.meta.env.VITE_API_URL}/api/v1`,
  nats_url: 'nats://localhost:4222',
};

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'success': return 'nd-badge nd-badge--success';
    case 'failed': return 'nd-badge nd-badge--failed';
    case 'in_progress':
    case 'pending': return 'nd-badge nd-badge--pending';
    default: return 'nd-badge nd-badge--none';
  }
}

function osIcon(os: string | null): string {
  switch (os) {
    case 'linux': return '🐧';
    case 'macos': return '🍎';
    case 'windows': return '🪟';
    default: return '💻';
  }
}

interface NodeDeploymentProps {
  onAuthError?: () => void;
}

export function NodeDeployment({ onAuthError }: NodeDeploymentProps = {}) {
  const [nodes, setNodes] = useState<InfraNode[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [scanning, setScanning] = useState(false);
  const [scanCidr, setScanCidr] = useState('192.168.1.0/24');
  const [scanMethod, setScanMethod] = useState<'ping' | 'nmap'>('ping');
  const [showManualAdd, setShowManualAdd] = useState(false);
  const [manualIp, setManualIp] = useState('');
  const [manualMac, setManualMac] = useState('');
  const [manualOs, setManualOs] = useState<'linux' | 'macos' | 'windows' | 'unknown'>('linux');
  const [deployModalOpen, setDeployModalOpen] = useState(false);
  const [deployConfig, setDeployConfig] = useState(defaultDeployConfig);
  const [error, setError] = useState<string | null>(null);
  const [deploying, setDeploying] = useState(false);
  const [editNode, setEditNode] = useState<InfraNode | null>(null);

  // ── Polling ──────────────────────────────────────────────────────────
  const fetchNodes = useCallback(async () => {
    try {
      const res = await axios.get<InfraNode[]>(`${API_BASE}/deployment/nodes`);
      setNodes(res.data);
    } catch { /* backend may not be up yet */ }
  }, []);

  useEffect(() => {
    fetchNodes();
    const id = setInterval(fetchNodes, 5000);
    return () => clearInterval(id);
  }, [fetchNodes]);

  // ── Selection helpers ─────────────────────────────────────────────────
  const toggleRow = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIds.size === nodes.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(nodes.map(n => n.id)));
    }
  };

  const allSelected = nodes.length > 0 && selectedIds.size === nodes.length;
  const someSelected = selectedIds.size > 0 && selectedIds.size < nodes.length;

  // ── Scan ──────────────────────────────────────────────────────────────
  const handleScan = async () => {
    setScanning(true);
    setError(null);
    try {
      await axios.post(`${API_BASE}/deployment/scan`, {
        network_cidr: scanCidr,
        method: scanMethod,
        timeout_seconds: 30,
      });
      await fetchNodes();
    } catch (e: unknown) {
      setError(axios.isAxiosError(e) ? (e.response?.data?.detail ?? e.message) : 'Scan failed');
    } finally {
      setScanning(false);
    }
  };

  // ── Manual add ────────────────────────────────────────────────────────
  const handleManualAdd = async () => {
    if (!manualIp.trim()) return;
    setError(null);
    try {
      await axios.post(`${API_BASE}/deployment/nodes`, {
        ip_address: manualIp.trim(),
        mac_address: manualMac.trim() || undefined,
        os_type: manualOs,
      });
      setManualIp('');
      setManualMac('');
      setShowManualAdd(false);
      await fetchNodes();
    } catch (e: unknown) {
      setError(axios.isAxiosError(e) ? (e.response?.data?.detail ?? e.message) : 'Add failed');
    }
  };

  // ── Deploy ────────────────────────────────────────────────────────────
  const openDeployModal = () => {
    // Pre-fill SSH username from the first selected node that has one stored
    const firstNode = nodes.find(n => selectedIds.has(n.id));
    setDeployConfig({
      ...defaultDeployConfig,
      ssh_username: firstNode?.ssh_username ?? '',
    });
    setDeployModalOpen(true);
  };

  const handleDeploy = async () => {
    setDeploying(true);
    setError(null);
    const targets = nodes.filter(n => selectedIds.has(n.id));
    try {
      await Promise.all(
        targets.map(node =>
          axios.post(`${API_BASE}/deployment/nodes/${node.id}/deploy`, {
            agent_type: deployConfig.agent_type,
            agent_subtype: deployConfig.agent_subtype,
            zone: deployConfig.zone,
            core_api_url: deployConfig.core_api_url,
            nats_url: deployConfig.nats_url,
            ssh_username: deployConfig.ssh_username || undefined,
            ssh_password: deployConfig.ssh_password || undefined,
          })
        )
      );
      setDeployModalOpen(false);
      setSelectedIds(new Set());
      await fetchNodes();
    } catch (e: unknown) {
      setError(axios.isAxiosError(e) ? (e.response?.data?.detail ?? e.message) : 'Deploy failed');
    } finally {
      setDeploying(false);
    }
  };

  const isDeploying = (n: InfraNode) =>
    n.deployment_status === 'pending' || n.deployment_status === 'in_progress';

  const selectedNodes = nodes.filter(n => selectedIds.has(n.id));
  const anySelectedDeploying = selectedNodes.some(isDeploying);

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="nd-container">

      {/* ── Header ── */}
      <div className="nd-header">
        <div className="nd-title">
          <Server className="nd-icon" />
          <span>Manage Infrastructure Nodes</span>
        </div>
        <span className="nd-count-pill">{nodes.length} node{nodes.length !== 1 ? 's' : ''}</span>
      </div>

      {/* ── Toolbar ── */}
      <div className="nd-toolbar">
        <div className="nd-toolbar-left">
          <input
            className="nd-input nd-input--cidr"
            value={scanCidr}
            onChange={e => setScanCidr(e.target.value)}
            placeholder="192.168.1.0/24"
            title="CIDR range to scan"
          />
          <select className="nd-select" value={scanMethod}
            onChange={e => setScanMethod(e.target.value as 'ping' | 'nmap')}>
            <option value="ping">Ping sweep</option>
            <option value="nmap">nmap</option>
          </select>
          <button className="nd-btn nd-btn--primary" onClick={handleScan} disabled={scanning}>
            {scanning
              ? <span className="nd-spinner" />
              : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13">
                <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>}
            {scanning ? 'Scanning…' : 'Scan Network'}
          </button>
          <button className="nd-btn nd-btn--secondary"
            onClick={() => setShowManualAdd(s => !s)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add Host
          </button>
        </div>

        <div className="nd-toolbar-right">
          {selectedIds.size > 0 && (
            <span className="nd-selection-info">
              {selectedIds.size} selected
            </span>
          )}
          <button
            className="nd-btn nd-btn--deploy"
            disabled={selectedIds.size === 0 || anySelectedDeploying}
            onClick={openDeployModal}
            title={selectedIds.size === 0 ? 'Select at least one node' : ''}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            Deploy to Selected ({selectedIds.size})
          </button>
        </div>
      </div>

      {/* ── Manual add form ── */}
      {showManualAdd && (
        <div className="nd-manual-add">
          <input className="nd-input" value={manualIp}
            onChange={e => setManualIp(e.target.value)}
            placeholder="IP address  e.g. 10.0.0.5"
            onKeyDown={e => e.key === 'Enter' && handleManualAdd()} />
          <input className="nd-input nd-input--mac" value={manualMac}
            onChange={e => setManualMac(e.target.value)}
            placeholder="MAC  e.g. AA:BB:CC:DD:EE:FF (optional)" />
          <select className="nd-select" value={manualOs}
            onChange={e => setManualOs(e.target.value as typeof manualOs)}>
            <option value="linux">Linux</option>
            <option value="macos">macOS</option>
            <option value="windows">Windows</option>
            <option value="unknown">Unknown</option>
          </select>
          <button className="nd-btn nd-btn--primary" onClick={handleManualAdd}>Save</button>
          <button className="nd-btn nd-btn--ghost" onClick={() => setShowManualAdd(false)}>Cancel</button>
        </div>
      )}

      {/* ── Error banner ── */}
      {error && (
        <div className="nd-error-banner">
          <span>{error}</span>
          <button className="nd-error-dismiss" onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* ── Node Table ── */}
      {nodes.length === 0 ? (
        <div className="nd-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="44" height="44">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <line x1="8" y1="21" x2="16" y2="21" />
            <line x1="12" y1="17" x2="12" y2="21" />
          </svg>
          <p>No nodes discovered.</p>
          <p className="nd-empty-hint">Run a scan or add a host manually.</p>
        </div>
      ) : (
        <div className="nd-table-wrapper">
          <table className="nd-table">
            <thead>
              <tr>
                <th className="nd-th nd-th--check">
                  <input
                    type="checkbox"
                    className="nd-checkbox"
                    checked={allSelected}
                    ref={el => { if (el) el.indeterminate = someSelected; }}
                    onChange={toggleAll}
                    title="Select all"
                  />
                </th>
                <th className="nd-th">Host</th>
                <th className="nd-th nd-th--ip">IP Address</th>
                <th className="nd-th nd-th--mac">MAC Address</th>
                <th className="nd-th nd-th--os">OS</th>
                <th className="nd-th nd-th--agent">Agent</th>
                <th className="nd-th nd-th--status">Status</th>
                <th className="nd-th nd-th--actions" />
              </tr>
            </thead>
            <tbody>
              {nodes.map(node => {
                const selected = selectedIds.has(node.id);
                return (
                  <tr
                    key={node.id}
                    className={`nd-tr ${selected ? 'nd-tr--selected' : ''} ${isDeploying(node) ? 'nd-tr--busy' : ''}`}
                    onClick={() => toggleRow(node.id)}
                  >
                    {/* Checkbox */}
                    <td className="nd-td nd-td--check" onClick={e => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        className="nd-checkbox"
                        checked={selected}
                        onChange={() => toggleRow(node.id)}
                        disabled={isDeploying(node)}
                      />
                    </td>

                    {/* Hostname */}
                    <td className="nd-td nd-td--host">
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span className="nd-hostname">
                          {node.hostname || <span className="nd-no-hostname">—</span>}
                        </span>
                        {node.error_message && (
                          <span className="nd-row-error" style={{ color: 'var(--accent-error)', fontSize: '0.75rem', marginTop: '2px' }}>
                            ⚠ {node.error_message}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* IP Address */}
                    <td className="nd-td nd-td--ip">
                      <span className="nd-monospace">{node.ip_address}</span>
                    </td>

                    {/* MAC Address */}
                    <td className="nd-td nd-td--mac">
                      {node.mac_address
                        ? <span className="nd-monospace nd-mac">{node.mac_address.toUpperCase()}</span>
                        : <span className="nd-unresolved">unresolved</span>}
                    </td>

                    {/* OS */}
                    <td className="nd-td nd-td--os">
                      <span className="nd-os">
                        <span className="nd-os-icon">{osIcon(node.os_type)}</span>
                        <span className="nd-os-label">{node.os_type ?? '—'}</span>
                      </span>
                    </td>

                    {/* Deployed agent */}
                    <td className="nd-td nd-td--agent">
                      {node.deployed_agent_type
                        ? <span className="nd-agent-pill">{node.deployed_agent_type}</span>
                        : <span className="nd-none">none</span>}
                    </td>

                    {/* Deployment status */}
                    <td className="nd-td nd-td--status">
                      <span className={statusBadgeClass(node.deployment_status)}>
                        {node.deployment_status}
                      </span>
                    </td>

                    {/* Actions */}
                    <td className="nd-td nd-td--actions" onClick={e => e.stopPropagation()}>
                      <button
                        className="nd-edit-btn"
                        title="Edit node"
                        onClick={() => setEditNode(node)}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="13" height="13">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                        Edit
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Deploy Modal ── */}
      {deployModalOpen && (
        <div className="nd-modal-overlay" onClick={() => !deploying && setDeployModalOpen(false)}>
          <div className="nd-modal" onClick={e => e.stopPropagation()}>

            <div className="nd-modal-header">
              <div>
                <h3>Deploy Agent</h3>
                <p className="nd-modal-subtitle">
                  {selectedIds.size} target{selectedIds.size !== 1 ? 's' : ''}:&nbsp;
                  <span className="nd-modal-targets">
                    {selectedNodes.map(n => n.ip_address).join(', ')}
                  </span>
                </p>
              </div>
            </div>

            <div className="nd-modal-body">
              {/* Agent type */}
              <div className="nd-field">
                <label>Agent Type</label>
                <div className="nd-radio-group">
                  {(['sentinel', 'striker'] as const).map(t => (
                    <label key={t} className={`nd-radio-card ${deployConfig.agent_type === t ? 'nd-radio-card--active' : ''}`}>
                      <input type="radio" name="agent_type" value={t}
                        checked={deployConfig.agent_type === t}
                        onChange={() => setDeployConfig(s => ({ ...s, agent_type: t }))} />
                      <span className="nd-radio-label">
                        {t === 'sentinel' ? '🛡 Sentinel' : '⚡ Striker'}
                      </span>
                      <span className="nd-radio-desc">
                        {t === 'sentinel' ? 'Monitoring agent' : 'Response agent'}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="nd-field-row">
                <div className="nd-field">
                  <label>Subtype</label>
                  <input className="nd-input" value={deployConfig.agent_subtype}
                    onChange={e => setDeployConfig(s => ({ ...s, agent_subtype: e.target.value }))} />
                </div>
                <div className="nd-field">
                  <label>Zone</label>
                  <input className="nd-input" value={deployConfig.zone}
                    onChange={e => setDeployConfig(s => ({ ...s, zone: e.target.value }))} />
                </div>
              </div>

              <div className="nd-modal-divider" />
              <p className="nd-modal-section-label">SSH Credentials</p>

              <div className="nd-field-row">
                <div className="nd-field">
                  <label>Username</label>
                  <input className="nd-input" value={deployConfig.ssh_username}
                    onChange={e => setDeployConfig(s => ({ ...s, ssh_username: e.target.value }))}
                    autoComplete="username" />
                </div>
                <div className="nd-field">
                  <label>Password</label>
                  <input className="nd-input" type="password" value={deployConfig.ssh_password}
                    onChange={e => setDeployConfig(s => ({ ...s, ssh_password: e.target.value }))}
                    autoComplete="current-password" />
                </div>
              </div>

              <div className="nd-modal-divider" />
              <p className="nd-modal-section-label">Connection</p>

              <div className="nd-field">
                <label>Core API URL</label>
                <input className="nd-input" value={deployConfig.core_api_url}
                  onChange={e => setDeployConfig(s => ({ ...s, core_api_url: e.target.value }))} />
              </div>
              <div className="nd-field">
                <label>NATS URL</label>
                <input className="nd-input" value={deployConfig.nats_url}
                  onChange={e => setDeployConfig(s => ({ ...s, nats_url: e.target.value }))} />
              </div>
            </div>

            <div className="nd-modal-footer">
              <button className="nd-btn nd-btn--secondary"
                onClick={() => setDeployModalOpen(false)} disabled={deploying}>
                Cancel
              </button>
              <button className="nd-btn nd-btn--primary" onClick={handleDeploy} disabled={deploying}>
                {deploying ? <><span className="nd-spinner nd-spinner--dark" />Deploying…</> : `Deploy to ${selectedIds.size} host${selectedIds.size !== 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Edit Node Modal ── */}
      {editNode && (
        <NodeEditModal
          node={editNode}
          onClose={() => setEditNode(null)}
          onSaved={() => { setEditNode(null); fetchNodes(); }}
          onAuthError={onAuthError}
        />
      )}
    </div>
  );
}
