import React, { useState, useEffect } from 'react';
import { Button, Table, Modal, Form, Input, Select, Switch, message } from 'antd';

const { Option } = Select;

interface ScheduledTask {
  id: string;
  name: string;
  description: string;
  schedule: string;
  task_type: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  last_run_at?: string;
  last_run_status?: string;
  next_run_at?: string;
}

const ScheduledTasks: React.FC = () => {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [modalVisible, setModalVisible] = useState<boolean>(false);
  const [editingTask, setEditingTask] = useState<ScheduledTask | null>(null);
  const [form] = Form.useForm();

  // Load tasks from API
  useEffect(() => {
    fetchTasks();
  }, []);

  const fetchTasks = async () => {
    try {
      setLoading(true);
      // Replace with actual API endpoint
      const response = await fetch('/api/scheduled-tasks/');
      const data = await response.json();
      setTasks(data);
    } catch (error) {
      message.error('Failed to fetch scheduled tasks');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTask = () => {
    setEditingTask(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEditTask = (task: ScheduledTask) => {
    setEditingTask(task);
    form.setFieldsValue({
      name: task.name,
      description: task.description,
      schedule: task.schedule,
      task_type: task.task_type,
      enabled: task.enabled,
    });
    setModalVisible(true);
  };

  const handleDeleteTask = async (taskId: string) => {
    try {
      await fetch(`/api/scheduled-tasks/${taskId}`, {
        method: 'DELETE',
      });
      message.success('Task deleted successfully');
      fetchTasks(); // Refresh the list
    } catch (error) {
      message.error('Failed to delete task');
    }
  };

  const handleToggleTask = async (taskId: string, enabled: boolean) => {
    try {
      const endpoint = enabled ?
        `/api/scheduled-tasks/${taskId}/enable` :
        `/api/scheduled-tasks/${taskId}/disable`;

      await fetch(endpoint, {
        method: 'PUT',
      });

      message.success(`Task ${enabled ? 'enabled' : 'disabled'} successfully`);
      fetchTasks(); // Refresh the list
    } catch (error) {
      message.error(`Failed to ${enabled ? 'enable' : 'disable'} task`);
    }
  };

  const handleManualTrigger = async (taskId: string) => {
    try {
      const response = await fetch(`/api/scheduled-tasks/${taskId}/trigger`, {
        method: 'POST',
      });

      if (response.ok) {
        message.success('Task triggered successfully');
      } else {
        message.error('Failed to trigger task');
      }
    } catch (error) {
      message.error('Failed to trigger task');
    }
  };

  const handleSaveTask = async (values: any) => {
    try {
      if (editingTask) {
        // Update existing task
        await fetch(`/api/scheduled-tasks/${editingTask.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(values),
        });
      } else {
        // Create new task
        await fetch('/api/scheduled-tasks/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(values),
        });
      }

      message.success(`Task ${editingTask ? 'updated' : 'created'} successfully`);
      setModalVisible(false);
      fetchTasks(); // Refresh the list
    } catch (error) {
      message.error(`Failed to ${editingTask ? 'update' : 'create'} task`);
    }
  };

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: 'Schedule',
      dataIndex: 'schedule',
      key: 'schedule',
    },
    {
      title: 'Type',
      dataIndex: 'task_type',
      key: 'task_type',
    },
    {
      title: 'Status',
      key: 'enabled',
      render: (_: any, record: ScheduledTask) => (
        <Switch
          checked={record.enabled}
          onChange={(checked) => handleToggleTask(record.id, checked)}
          checkedChildren="Active"
          unCheckedChildren="Inactive"
        />
      ),
    },
    {
      title: 'Last Run',
      dataIndex: 'last_run_at',
      key: 'last_run_at',
      render: (date: string) => date ? new Date(date).toLocaleString() : 'Never',
    },
    {
      title: 'Next Run',
      dataIndex: 'next_run_at',
      key: 'next_run_at',
      render: (date: string) => date ? new Date(date).toLocaleString() : 'Not scheduled',
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, record: ScheduledTask) => (
        <>
          <Button
            type="link"
            onClick={() => handleManualTrigger(record.id)}
            disabled={!record.enabled}
          >
            Run Now
          </Button>
          <Button type="link" onClick={() => handleEditTask(record)}>
            Edit
          </Button>
          <Button
            type="link"
            danger
            onClick={() => handleDeleteTask(record.id)}
          >
            Delete
          </Button>
        </>
      ),
    },
  ];

  return (
    <div className="scheduled-tasks">
      <div style={{ marginBottom: 16 }}>
        <Button type="primary" onClick={handleCreateTask}>
          Create Scheduled Task
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={tasks}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title={editingTask ? 'Edit Scheduled Task' : 'Create Scheduled Task'}
        visible={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSaveTask}
        >
          <Form.Item
            name="name"
            label="Task Name"
            rules={[{ required: true, message: 'Please input task name!' }]}
          >
            <Input placeholder="Enter task name" />
          </Form.Item>

          <Form.Item
            name="description"
            label="Description"
          >
            <Input.TextArea rows={3} placeholder="Enter task description" />
          </Form.Item>

          <Form.Item
            name="schedule"
            label="Schedule (Cron Expression)"
            rules={[{ required: true, message: 'Please input schedule!' }]}
          >
            <Input placeholder="e.g., @hourly, 0 9 * * *, etc." />
          </Form.Item>

          <Form.Item
            name="task_type"
            label="Task Type"
            rules={[{ required: true, message: 'Please select task type!' }]}
          >
            <Select placeholder="Select task type">
              <Option value="health_check">Health Check</Option>
              <Option value="data_cleanup">Data Cleanup</Option>
              <Option value="report_generation">Report Generation</Option>
              <Option value="backup">Backup</Option>
              <Option value="notification">Notification</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="enabled"
            label="Enabled"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit">
              {editingTask ? 'Update' : 'Create'} Task
            </Button>
            <Button
              style={{ marginLeft: 8 }}
              onClick={() => setModalVisible(false)}
            >
              Cancel
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ScheduledTasks;