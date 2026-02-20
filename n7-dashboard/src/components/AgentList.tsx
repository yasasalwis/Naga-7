import { useState, useEffect } from 'react';
import axios from 'axios';
import { Shield } from 'lucide-react';
import './AgentList.css';

interface Agent {
  id: string;
  agent_type: string;
  agent_subtype: string;
  status: string;
  last_heartbeat: string;
}

export function AgentList() {
  const [agents, setAgents] = useState<Agent[]>([]);

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
        Active Agents
      </h2>
      <div className="agent-items">
        {agents.length === 0 ? (
          <p className="no-agents">No agents connected.</p>
        ) : (
          agents.map((agent) => (
            <div key={agent.id} className="agent-card">
              <div className="agent-info">
                <h3>{agent.id}</h3>
                <p className="agent-meta">
                  {agent.agent_type} • {agent.agent_subtype}
                </p>
                <p className="agent-heartbeat">
                  Last Heartbeat: {new Date(agent.last_heartbeat).toLocaleTimeString()}
                </p>
              </div>
              <div className="agent-status-container">
                <span className={`agent-status ${agent.status === 'active' ? 'active' : 'inactive'}`}>
                  {agent.status}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
