import React, { useState, useEffect } from 'react';
import './SubAgentControls.css';

interface SubAgent {
  id: string;
  name: string;
  role: string;
  description: string;
  activated_status: boolean;
  activation_timestamp?: string;
  deactivation_timestamp?: string;
  timeout_duration: number;
  created_at: string;
  updated_at: string;
}

interface SubAgentControlsProps {
  sessionId?: string;
  availableAgents: SubAgent[];
  onAgentToggle?: (agentId: string, activate: boolean) => void;
  onAgentCommand?: (command: string) => void;
}

const SubAgentControls: React.FC<SubAgentControlsProps> = ({
  sessionId,
  availableAgents,
  onAgentToggle,
  onAgentCommand
}) => {
  const [activeAgents, setActiveAgents] = useState<SubAgent[]>([]);
  const [command, setCommand] = useState('');

  useEffect(() => {
    // Update active agents when availableAgents changes
    const active = availableAgents.filter(agent => agent.activated_status);
    setActiveAgents(active);
  }, [availableAgents]);

  const handleAgentToggle = (agentId: string, activate: boolean) => {
    if (onAgentToggle) {
      onAgentToggle(agentId, activate);
    }
  };

  const handleCommandSubmit = () => {
    if (command.trim() && onAgentCommand) {
      onAgentCommand(command);
      setCommand('');
    }
  };

  const handleCommandKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleCommandSubmit();
    }
  };

  return (
    <div className="subagent-controls">
      <div className="controls-header">
        <h2>SubAgent Controls {sessionId && <span>(Session: {sessionId.substring(0, 8)}...)</span>}</h2>
      </div>

      <div className="available-agents">
        <h3>Available SubAgents</h3>
        <div className="agent-grid">
          {availableAgents.map(agent => (
            <div key={agent.id} className="agent-card">
              <div className="agent-info">
                <h4>{agent.name}</h4>
                <p className="agent-role">Role: {agent.role}</p>
                <p className="agent-description">{agent.description}</p>

                <div className="agent-status">
                  Status: <span className={agent.activated_status ? 'status-active' : 'status-inactive'}>
                    {agent.activated_status ? 'Active' : 'Inactive'}
                  </span>
                </div>

                <div className="agent-meta">
                  <div>Timeout: {agent.timeout_duration}s</div>
                  <div>Created: {new Date(agent.created_at).toLocaleDateString()}</div>
                </div>
              </div>

              <div className="agent-actions">
                <button
                  className={`action-btn ${agent.activated_status ? 'deactivate' : 'activate'}`}
                  onClick={() => handleAgentToggle(agent.id, !agent.activated_status)}
                >
                  {agent.activated_status ? 'Deactivate' : 'Activate'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="active-agents">
        <h3>Active SubAgents</h3>
        {activeAgents.length > 0 ? (
          <div className="active-agent-list">
            {activeAgents.map(agent => (
              <div key={agent.id} className="active-agent-item">
                <span className="agent-name">{agent.name}</span>
                <span className="agent-role">({agent.role})</span>
                {agent.activation_timestamp && (
                  <span className="activation-time">
                    Active since: {new Date(agent.activation_timestamp).toLocaleTimeString()}
                  </span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="no-active-agents">No active subagents</div>
        )}
      </div>

      <div className="command-interface">
        <h3>Agent Command Interface</h3>
        <div className="command-input-group">
          <input
            type="text"
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyPress={handleCommandKeyPress}
            placeholder="Enter command for subagent (e.g., /subagent coder 'implement bubble sort')"
          />
          <button onClick={handleCommandSubmit} className="submit-command">
            Submit
          </button>
        </div>
        <div className="command-help">
          <p>Available commands:</p>
          <ul>
            <li><code>/subagent &lt;role&gt;</code> - Activate a specific subagent (coder, researcher, reviewer)</li>
            <li><code>/subagent off</code> - Deactivate current subagent</li>
            <li><code>/subagent list</code> - List available subagents</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default SubAgentControls;