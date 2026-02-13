import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import ChatInterface from './components/ChatInterface';
import TaskVisualization from './components/TaskVisualization';
import SubAgentControls from './components/SubAgentControls';
import HeartbeatMonitor from './components/HeartbeatMonitor';
import ScheduledTasks from './components/ScheduledTasks';
import './App.css';

function App() {
  const [sessionId, setSessionId] = useState<string>(() => {
    // Retrieve session ID from localStorage or generate a new one
    const savedSessionId = localStorage.getItem('sessionId');
    return savedSessionId || `session_${Date.now()}`;
  });

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
                    <SubAgentControls />
                  </div>

                  <div className="sidebar-section">
                    <h3>Heartbeat Monitor</h3>
                    <HeartbeatMonitor />
                  </div>

                  <div className="sidebar-section">
                    <h3>Scheduled Tasks</h3>
                    <ScheduledTasks />
                  </div>
                </div>

                <div className="visualization-section">
                  <h3>Task Visualization</h3>
                  <TaskVisualization />
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