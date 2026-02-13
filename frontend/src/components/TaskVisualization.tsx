import React, { useState, useEffect } from 'react';
import './TaskVisualization.css';

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

interface TaskVisualizationProps {
  sessionId?: string;
  tasks: Task[];
  onSelectTask?: (task: Task) => void;
}

const TaskVisualization: React.FC<TaskVisualizationProps> = ({
  sessionId,
  tasks,
  onSelectTask
}) => {
  const [filteredTasks, setFilteredTasks] = useState<Task[]>(tasks);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [sortBy, setSortBy] = useState<string>('created_at');

  useEffect(() => {
    let result = [...tasks];

    // Apply status filter
    if (filterStatus !== 'all') {
      result = result.filter(task => task.status === filterStatus);
    }

    // Apply sorting
    result.sort((a, b) => {
      if (sortBy === 'priority') {
        const priorityOrder = { critical: 4, high: 3, medium: 2, low: 1 };
        return priorityOrder[b.priority] - priorityOrder[a.priority];
      } else if (sortBy === 'status') {
        return a.status.localeCompare(b.status);
      } else {
        // Sort by creation date (newest first)
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
    });

    setFilteredTasks(result);
  }, [tasks, filterStatus, sortBy]);

  const getStatusColor = (status: string) => {
    switch(status) {
      case 'completed': return '#28a745';
      case 'in_progress': return '#007bff';
      case 'failed': return '#dc3545';
      case 'cancelled': return '#6c757d';
      case 'paused': return '#ffc107';
      default: return '#17a2b8';
    }
  };

  const getPriorityClass = (priority: string) => {
    return `priority-${priority}`;
  };

  return (
    <div className="task-visualization">
      <div className="task-header">
        <h2>Task Visualization {sessionId && <span>({sessionId.substring(0, 8)}...)</span>}</h2>
        <div className="task-controls">
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="filter-select"
          >
            <option value="all">All Statuses</option>
            <option value="created">Created</option>
            <option value="planned">Planned</option>
            <option value="assigned">Assigned</option>
            <option value="in_progress">In Progress</option>
            <option value="paused">Paused</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="sort-select"
          >
            <option value="created_at">Sort by Date</option>
            <option value="priority">Sort by Priority</option>
            <option value="status">Sort by Status</option>
          </select>
        </div>
      </div>

      <div className="task-list">
        {filteredTasks.length > 0 ? (
          filteredTasks.map(task => (
            <div
              key={task.id}
              className={`task-item ${getPriorityClass(task.priority)}`}
              onClick={() => onSelectTask && onSelectTask(task)}
            >
              <div className="task-header-info">
                <div className="task-title">{task.title}</div>
                <div className="task-status" style={{ backgroundColor: getStatusColor(task.status) }}>
                  {task.status.replace('_', ' ')}
                </div>
              </div>

              <div className="task-description">
                {task.description}
              </div>

              <div className="task-details">
                <div className="detail-item">
                  <span className="detail-label">Assigned to:</span>
                  <span className="detail-value">{task.assigned_to}</span>
                </div>

                {task.sub_agent_role && (
                  <div className="detail-item">
                    <span className="detail-label">Sub-agent:</span>
                    <span className="detail-value">{task.sub_agent_role}</span>
                  </div>
                )}

                <div className="detail-item">
                  <span className="detail-label">Priority:</span>
                  <span className="detail-value">{task.priority}</span>
                </div>

                {task.estimated_duration && (
                  <div className="detail-item">
                    <span className="detail-label">Duration:</span>
                    <span className="detail-value">{task.estimated_duration}s</span>
                  </div>
                )}
              </div>

              <div className="task-timeline">
                <div className="timeline-item">
                  <span className="timeline-label">Created:</span>
                  <span className="timeline-value">{new Date(task.created_at).toLocaleString()}</span>
                </div>

                {task.started_at && (
                  <div className="timeline-item">
                    <span className="timeline-label">Started:</span>
                    <span className="timeline-value">{new Date(task.started_at).toLocaleString()}</span>
                  </div>
                )}

                {task.completed_at && (
                  <div className="timeline-item">
                    <span className="timeline-label">Completed:</span>
                    <span className="timeline-value">{new Date(task.completed_at).toLocaleString()}</span>
                  </div>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="no-tasks">
            No tasks found with the current filters
          </div>
        )}
      </div>
    </div>
  );
};

export default TaskVisualization;