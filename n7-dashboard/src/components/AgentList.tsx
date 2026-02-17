import { useState, useEffect } from 'react';
import axios from 'axios';
import { Shield, ShieldAlert, Cpu } from 'lucide-react';

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
        const response = await axios.get('http://localhost:8000/api/agents/');
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
    <div className="bg-white shadow rounded-lg p-6">
      <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
        <Shield className="w-6 h-6 text-blue-600" />
        Active Agents
      </h2>
      <div className="space-y-4">
        {agents.length === 0 ? (
          <p className="text-gray-500">No agents connected.</p>
        ) : (
          agents.map((agent) => (
            <div key={agent.id} className="border p-4 rounded-md flex justify-between items-center bg-gray-50">
              <div>
                <p className="font-semibold text-lg">{agent.id}</p>
                <p className="text-sm text-gray-600 capitalize">
                  {agent.agent_type} • {agent.agent_subtype}
                </p>
                <p className="text-xs text-gray-400 mt-1">Last Heartbeat: {new Date(agent.last_heartbeat).toLocaleTimeString()}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`px-2 py-1 text-xs rounded-full ${agent.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}>
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
