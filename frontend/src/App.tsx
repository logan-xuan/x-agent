import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import ChatInterface from './components/ChatInterface';
import TaskVisualization from './components/TaskVisualization';
import SubAgentControls from './components/SubAgentControls';
import HeartbeatMonitor from './components/HeartbeatMonitor';
// import ScheduledTasks from './components/ScheduledTasks'; // Temporarily disabled
import './App.css';

// Define types based on component interfaces
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

interface Task {
  id: string;
  title: string;
  description: string;
  status: 'created' | 'planned' | 'assigned' | 'in_progress' | 'paused' | 'completed' | 'failed' | 'cancelled';
  assigned_to: string;
  sub_agent_role?: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
  estimated_duration?: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

function App() {
  const [sessionId] = useState<string>(() => {
    // Retrieve session ID from localStorage or generate a new one
    const savedSessionId = localStorage.getItem('sessionId');
    return savedSessionId || `session_${Date.now()}`;
  });

  // Mock data for required props
  const [availableAgents] = useState<SubAgent[]>([
    {
      id: '1',
      name: 'Research Agent',
      role: 'researcher',
      description: 'Handles research and information gathering tasks',
      activated_status: false,
      timeout_duration: 300,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    },
    {
      id: '2',
      name: 'Code Agent',
      role: 'coder',
      description: 'Handles coding and development tasks',
      activated_status: false,
      timeout_duration: 300,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    },
    {
      id: '3',
      name: 'Review Agent',
      role: 'reviewer',
      description: 'Reviews and validates code and content',
      activated_status: false,
      timeout_duration: 300,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    }
  ]);

  const [tasks] = useState<Task[]>([
    {
      id: '1',
      title: 'Setup project structure',
      description: 'Initialize the project with proper directory structure',
      status: 'completed',
      assigned_to: 'Code Agent',
      sub_agent_role: 'coder',
      priority: 'high',
      estimated_duration: 120,
      created_at: new Date().toISOString(),
      started_at: new Date().toISOString(),
      completed_at: new Date().toISOString()
    },
    {
      id: '2',
      title: 'Implement authentication',
      description: 'Create user authentication system',
      status: 'in_progress',
      assigned_to: 'Code Agent',
      sub_agent_role: 'coder',
      priority: 'critical',
      estimated_duration: 300,
      created_at: new Date().toISOString(),
      started_at: new Date().toISOString()
    },
    {
      id: '3',
      title: 'Research AI models',
      description: 'Investigate available AI models for integration',
      status: 'planned',
      assigned_to: 'Research Agent',
      sub_agent_role: 'researcher',
      priority: 'medium',
      estimated_duration: 240,
      created_at: new Date().toISOString()
    }
  ]);

  // Save session ID to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('sessionId', sessionId);
  }, [sessionId]);

  return (
    <Router>
      <div className="App">
        <header className="app-header">
          <h1>x-agent2 Dashboard</h1>
          <div className="session-info">
            Session: {sessionId.substring(0, 8)}...
          </div>
        </header>

        <main className="app-main">
          <Routes>
            <Route path="/" element={
              <div className="dashboard-grid">
                <div className="chat-section">
                  <ChatInterface
                    sessionId={sessionId}
                  />
                </div>

                <div className="sidebar">
                  <div className="sidebar-section">
                    <h3>Sub-Agent Controls</h3>
                    <SubAgentControls
                      sessionId={sessionId}
                      availableAgents={availableAgents}
                    />
                  </div>

                  <div className="sidebar-section">
                    <h3>Heartbeat Monitor</h3>
                    <HeartbeatMonitor />
                  </div>

                  {/* Temporarily disabled scheduled tasks
                  <div className="sidebar-section">
                    <h3>Scheduled Tasks</h3>
                    <ScheduledTasks />
                  </div>
                  */}
                </div>

                <div className="visualization-section">
                  <h3>Task Visualization</h3>
                  <TaskVisualization
                    sessionId={sessionId}
                    tasks={tasks}
                  />
                </div>
              </div>
            } />

            <Route path="/chat" element={
              <div className="chat-full-page">
                <ChatInterface
                  sessionId={sessionId}
                />
              </div>
            } />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;