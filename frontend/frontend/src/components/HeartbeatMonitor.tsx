import React, { useState, useEffect } from 'react';
import './HeartbeatMonitor.css';

interface TaskProgress {
  taskId: string;
  taskName: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number; // 0-100 percentage
  startTime: Date;
  estimatedTimeRemaining?: number; // in seconds
  message: string;
}

interface HeartbeatMonitorProps {
  onTaskCancel?: (taskId: string) => void;
  defaultTasks?: TaskProgress[];
}

const HeartbeatMonitor: React.FC<HeartbeatMonitorProps> = ({
  onTaskCancel,
  defaultTasks = []
}) => {
  const [tasks, setTasks] = useState<TaskProgress[]>(defaultTasks);
  const [isMonitoring, setIsMonitoring] = useState(true);

  // Simulate adding tasks for demo
  useEffect(() => {
    if (defaultTasks.length === 0) {
      // Add some sample tasks for demonstration
      const sampleTasks: TaskProgress[] = [
        {
          taskId: '1',
          taskName: 'Generating report',
          status: 'running',
          progress: 45,
          startTime: new Date(Date.now() - 120000), // 2 minutes ago
          estimatedTimeRemaining: 90,
          message: 'Processing data sets...'
        },
        {
          taskId: '2',
          taskName: 'Analyzing code',
          status: 'queued',
          progress: 0,
          startTime: new Date(),
          message: 'Waiting to start...'
        },
        {
          taskId: '3',
          taskName: 'Uploading files',
          status: 'completed',
          progress: 100,
          startTime: new Date(Date.now() - 300000), // 5 minutes ago
          message: 'Successfully uploaded 3 files'
        }
      ];
      setTasks(sampleTasks);
    }
  }, [defaultTasks]);

  // Simulate progress updates
  useEffect(() => {
    if (!isMonitoring) return;

    const interval = setInterval(() => {
      setTasks(prevTasks => {
        return prevTasks.map(task => {
          if (task.status === 'running' && task.progress < 100) {
            // Simulate progress
            const increment = Math.random() * 5; // Random increment up to 5%
            const newProgress = Math.min(task.progress + increment, 100);

            // Calculate new estimated time
            const elapsed = (new Date().getTime() - task.startTime.getTime()) / 1000; // in seconds
            const estimatedTotal = newProgress > 0 ? elapsed / (newProgress / 100) : 60;
            const estimatedRemaining = estimatedTotal - elapsed;

            return {
              ...task,
              progress: newProgress,
              estimatedTimeRemaining: Math.max(0, estimatedRemaining),
              message: newProgress >= 100
                ? 'Finalizing task...'
                : `Processing, ${Math.round(newProgress)}% complete`
            };
          }
          return task;
        });
      });
    }, 2000); // Update every 2 seconds

    return () => clearInterval(interval);
  }, [isMonitoring]);

  const handleCancelTask = (taskId: string) => {
    setTasks(prevTasks => {
      return prevTasks.map(task =>
        task.taskId === taskId
          ? { ...task, status: 'cancelled', message: 'Task was cancelled by user' }
          : task
      );
    });

    if (onTaskCancel) {
      onTaskCancel(taskId);
    }
  };

  const getStatusColor = (status: string) => {
    switch(status) {
      case 'completed': return '#28a745';
      case 'running': return '#007bff';
      case 'failed': return '#dc3545';
      case 'cancelled': return '#6c757d';
      case 'queued': return '#ffc107';
      default: return '#17a2b8';
    }
  };

  const getStatusText = (status: string) => {
    switch(status) {
      case 'completed': return 'Completed';
      case 'running': return 'In Progress';
      case 'failed': return 'Failed';
      case 'cancelled': return 'Cancelled';
      case 'queued': return 'Queued';
      default: return status;
    }
  };

  const formatTime = (seconds?: number) => {
    if (seconds === undefined || seconds <= 0) return '--';

    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="heartbeat-monitor">
      <div className="monitor-header">
        <h2>Long-Running Task Monitor</h2>
        <div className="monitor-controls">
          <button
            className={`control-btn ${isMonitoring ? 'pause' : 'play'}`}
            onClick={() => setIsMonitoring(!isMonitoring)}
          >
            {isMonitoring ? '⏸ Pause Monitoring' : '▶ Resume Monitoring'}
          </button>
        </div>
      </div>

      <div className="task-list">
        {tasks.length > 0 ? (
          tasks.map(task => (
            <div key={task.taskId} className="task-item">
              <div className="task-header">
                <div className="task-info">
                  <h3 className="task-name">{task.taskName}</h3>
                  <div className="task-status" style={{ backgroundColor: getStatusColor(task.status) }}>
                    {getStatusText(task.status)}
                  </div>
                </div>

                <div className="task-actions">
                  {task.status === 'running' && (
                    <button
                      className="cancel-btn"
                      onClick={() => handleCancelTask(task.taskId)}
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>

              <div className="task-progress-container">
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${task.progress}%` }}
                  ></div>
                </div>
                <div className="progress-text">{Math.round(task.progress)}%</div>
              </div>

              <div className="task-details">
                <div className="detail-row">
                  <div className="detail-item">
                    <span className="label">Started:</span>
                    <span className="value">
                      {task.startTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  <div className="detail-item">
                    <span className="label">Est. Remaining:</span>
                    <span className="value">{formatTime(task.estimatedTimeRemaining)}</span>
                  </div>
                </div>

                <div className="task-message">
                  {task.message}
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="no-tasks">
            No long-running tasks to monitor
          </div>
        )}
      </div>
    </div>
  );
};

export default HeartbeatMonitor;