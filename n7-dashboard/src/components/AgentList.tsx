import { useState, useEffect } from 'react';
import axios from 'axios';
import { Shield, ChevronDown, ChevronRight, Settings } from 'lucide-react';
import './AgentList.css';
import { AgentConfigModal } from './AgentConfigModal';

interface NodeMetadata {
  hostname?: string;
  os_name?: string;
  os_version?: string;
  kernel_version?: string;
  cpu_model?: string;
  cpu_cores?: number;
  ram_total_mb?: number;
  mac_address?: string;
  python_version?: string;
  agent_version?: string;
}

interface Agent {
  id: string;
  agent_type: string;
  agent_subtype: string;
  status: string;
  last_heartbeat: string;
  node_metadata?: NodeMetadata | null;
}

interface AgentListProps {
  onAuthError?: () => void;
}

export function AgentList({ onAuthError }: AgentListProps) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [expandedMeta, setExpandedMeta] = useState<Set<string>>(new Set());
  const [configuringAgentId, setConfiguringAgentId] = useState<string | null>(null);
  const [configuringAgentType, setConfiguringAgentType] = useState<string>('');

  const toggleMeta = (agentId: string) => {
    setExpandedMeta(prev => {
      const next = new Set(prev);
      next.has(agentId) ? next.delete(agentId) : next.add(agentId);
      return next;
    });
  };

  useEffect(() => {
    const fetchAgents = async () => {
      try {
        const response = await axios.get(`${import.meta.env.VITE_API_URL}/api/v1/agents/`);
        setAgents(response.data);
      } catch (error) {
        console.error('Failed to fetch agents', error);
      }
    };

    fetchAgents();
    const interval = setInterval(fetchAgents, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="agent-list-container">
      <h2 className="agent-list-header">
        <Shield className="agent-list-title-icon" size={24} />
        Active Security Agents
      </h2>
      <div className="agent-items">
        {agents.length === 0 ? (
          <p className="no-agents">No agents connected.</p>
        ) : (
          agents.map((agent) => (
            <div key={agent.id} className="agent-card">
              <div className="agent-card-main">
                <div className="agent-info">
                  <h3>{agent.id}</h3>
                  <p className="agent-meta">
                    {agent.agent_type} • {agent.agent_subtype}
                  </p>
                  <p className="agent-heartbeat">
                    Last Heartbeat: {new Date(agent.last_heartbeat + 'Z').toLocaleTimeString()}
                  </p>
                </div>
                <div className="agent-status-container">
                  <span className={`agent-status ${agent.status === 'active' ? 'active' : 'inactive'}`}>
                    {agent.status}
                  </span>
                  <button
                    className="agent-configure-btn"
                    onClick={() => {
                      setConfiguringAgentId(agent.id);
                      setConfiguringAgentType(agent.agent_type);
                    }}
                    title="Configure agent"
                  >
                    <Settings size={14} />
                    <span>Configure</span>
                  </button>
                  {agent.node_metadata && (
                    <button
                      className="agent-meta-toggle"
                      onClick={() => toggleMeta(agent.id)}
                      title="Toggle node details"
                    >
                      {expandedMeta.has(agent.id)
                        ? <ChevronDown size={14} />
                        : <ChevronRight size={14} />}
                      <span>System Details</span>
                    </button>
                  )}
                </div>
              </div>

              {expandedMeta.has(agent.id) && agent.node_metadata && (
                <div className="agent-node-metadata">
                  <div className="node-meta-grid">
                    {agent.node_metadata.hostname && (
                      <div className="node-meta-item">
                        <span className="node-meta-label">Hostname</span>
                        <span className="node-meta-value">{agent.node_metadata.hostname}</span>
                      </div>
                    )}
                    {(agent.node_metadata.os_name || agent.node_metadata.kernel_version) && (
                      <div className="node-meta-item">
                        <span className="node-meta-label">OS</span>
                        <span className="node-meta-value">
                          {agent.node_metadata.os_name} {agent.node_metadata.kernel_version}
                        </span>
                      </div>
                    )}
                    {agent.node_metadata.cpu_model && (
                      <div className="node-meta-item">
                        <span className="node-meta-label">CPU</span>
                        <span className="node-meta-value">
                          {agent.node_metadata.cpu_model}
                          {agent.node_metadata.cpu_cores ? ` (${agent.node_metadata.cpu_cores} cores)` : ''}
                        </span>
                      </div>
                    )}
                    {agent.node_metadata.ram_total_mb != null && (
                      <div className="node-meta-item">
                        <span className="node-meta-label">RAM</span>
                        <span className="node-meta-value">
                          {(agent.node_metadata.ram_total_mb / 1024).toFixed(1)} GB
                        </span>
                      </div>
                    )}
                    {agent.node_metadata.mac_address && (
                      <div className="node-meta-item">
                        <span className="node-meta-label">MAC</span>
                        <span className="node-meta-value">{agent.node_metadata.mac_address}</span>
                      </div>
                    )}
                    {agent.node_metadata.python_version && (
                      <div className="node-meta-item">
                        <span className="node-meta-label">Python</span>
                        <span className="node-meta-value">{agent.node_metadata.python_version}</span>
                      </div>
                    )}
                    {agent.node_metadata.agent_version && (
                      <div className="node-meta-item">
                        <span className="node-meta-label">Agent</span>
                        <span className="node-meta-value">v{agent.node_metadata.agent_version}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {configuringAgentId && (
        <AgentConfigModal
          agentId={configuringAgentId}
          agentType={configuringAgentType}
          onClose={() => setConfiguringAgentId(null)}
          onAuthError={onAuthError}
        />
      )}
    </div>
  );
}
