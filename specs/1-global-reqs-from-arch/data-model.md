# Data Model: 全局架构需求定义

## Core Entities

### User
- **Fields**:
  - id (UUID): Unique identifier
  - username (string): Display name/handle
  - email (string, optional): Contact email
  - preferences (JSON): User-specific settings
  - created_at (datetime): Account creation timestamp
  - last_active (datetime): Last interaction timestamp
  - permissions (string[]): User permissions/roles

- **Relationships**:
  - One-to-many with Session
  - One-to-many with MemoryEntry
  - Many-to-many with Plugin (through UserPlugin)

- **Validation Rules**:
  - Username must be 3-30 characters
  - Email must be valid format if provided
  - Permissions must be predefined values

### Session
- **Fields**:
  - id (UUID): Unique identifier
  - user_id (UUID): Foreign key to User
  - started_at (datetime): Session start timestamp
  - last_interaction_at (datetime): Last message timestamp
  - context_data (JSON): Serialized conversation context
  - active_status (enum: active, paused, archived)
  - session_metadata (JSON): Additional session properties

- **Relationships**:
  - Belongs to User
  - One-to-many with Message
  - One-to-many with InteractionTrace

- **State Transitions**:
  - Created → Active (on first interaction)
  - Active → Paused (after inactivity)
  - Active/Paused → Archived (on user request or expiration)

### Message
- **Fields**:
  - id (UUID): Unique identifier
  - session_id (UUID): Foreign key to Session
  - sender_type (enum: user, assistant, system): Who sent the message
  - sender_id (UUID, optional): Specific user or system component
  - content (text): Message content
  - content_type (enum: text, image, file, tool_result): Type of content
  - content_metadata (JSON): Additional content-specific data
  - timestamp (datetime): When message was created
  - processed_status (enum: pending, processing, completed, error)

- **Relationships**:
  - Belongs to Session
  - One-to-one with ToolExecution (if tool result)

- **Validation Rules**:
  - Content must not exceed size limits
  - File content must pass security validation

### MemoryEntry
- **Fields**:
  - id (UUID): Unique identifier
  - user_id (UUID): Foreign key to User
  - entry_type (enum: preference, fact, interaction, summary): Type of memory
  - content (text): Memory content
  - embedding_vector (binary): Vector representation for semantic search
  - relevance_score (float): How relevant this memory is (0.0-1.0)
  - created_at (datetime): When memory was created
  - last_accessed_at (datetime): When memory was last used
  - expiry_date (datetime, optional): When memory expires
  - tags (string[]): Associated tags for organization

- **Relationships**:
  - Belongs to User
  - Many-to-many with Session (through MemorySession)

- **Validation Rules**:
  - Relevance score between 0.0 and 1.0
  - Tags must be predefined or user-created

### Plugin
- **Fields**:
  - id (UUID): Unique identifier
  - name (string): Plugin name
  - description (text): Detailed description
  - version (string): Version identifier
  - author (string): Plugin author
  - manifest_path (string): Path to plugin manifest file
  - enabled_status (boolean): Whether plugin is active
  - permissions_needed (JSON): Permissions plugin requires
  - installation_date (datetime): When plugin was installed
  - settings_schema (JSON): Configurable settings definition

- **Relationships**:
  - Many-to-many with User (through UserPlugin)
  - One-to-many with PluginExecution

- **Validation Rules**:
  - Name must be unique
  - Version must follow semantic versioning
  - Permissions must be predefined

### ToolExecution
- **Fields**:
  - id (UUID): Unique identifier
  - session_id (UUID): Foreign key to Session
  - message_id (UUID): Foreign key to Message that triggered execution
  - tool_name (string): Name of the tool being executed
  - parameters (JSON): Parameters passed to the tool
  - execution_status (enum: queued, running, succeeded, failed, cancelled)
  - started_at (datetime): When execution started
  - completed_at (datetime, optional): When execution completed
  - result_data (JSON): Result of tool execution
  - error_message (text, optional): Error if execution failed
  - execution_metadata (JSON): Execution-specific metadata

- **Relationships**:
  - Belongs to Session and Message

- **State Transitions**:
  - Queued → Running (when picked up for execution)
  - Running → Succeeded/Failed/Cancelled (when complete)

### SubAgent
- **Fields**:
  - id (UUID): Unique identifier
  - name (string): SubAgent name (e.g., "coder", "researcher", "reviewer")
  - role (string): The specialized role of this SubAgent
  - description (text): Description of what this SubAgent does
  - prompt (text): System prompt for this SubAgent
  - activated_status (boolean): Whether the SubAgent is currently activated
  - activation_timestamp (datetime, optional): When the SubAgent was activated
  - deactivation_timestamp (datetime, optional): When the SubAgent was deactivated
  - session_id (UUID, optional): Session where the SubAgent is active
  - timeout_duration (int): Auto-deactivation timeout in seconds
  - created_at (datetime): When SubAgent was registered
  - updated_at (datetime): When SubAgent configuration was last updated

- **Relationships**:
  - Optionally belongs to Session (when active)
  - One-to-many with SubAgentExecution

- **Validation Rules**:
  - Role must be a predefined role
  - Only one instance of each SubAgent type per session
  - Activation requires proper user permissions

### Task
- **Fields**:
  - id (UUID): Unique identifier
  - session_id (UUID): Foreign key to Session where task was created
  - parent_task_id (UUID, optional): Foreign key to parent task if this is a sub-task
  - title (string): Brief description of the task
  - description (text): Detailed description of the task
  - task_type (enum: planning, research, coding, review, execution, coordination): Type of task
  - priority (enum: low, medium, high, critical): Priority level
  - assigned_to (enum: main_agent, sub_agent, tool, external_service): Who will execute this task
  - sub_agent_role (string, optional): Role name if assigned to sub-agent
  - status (enum: created, planned, assigned, in_progress, paused, completed, failed, cancelled): Current status
  - estimated_duration (int, optional): Estimated completion time in seconds
  - actual_duration (int, optional): Actual time taken in seconds
  - created_at (datetime): When task was created
  - started_at (datetime, optional): When task execution started
  - completed_at (datetime, optional): When task was completed
  - dependencies (UUID[]): List of task IDs this task depends on
  - result (text, optional): Result/output of the task
  - error_message (text, optional): Error details if task failed

- **Relationships**:
  - Belongs to Session
  - Optionally has parent Task (for hierarchical tasks)
  - One-to-many with TaskExecutionTrace

- **State Transitions**:
  - Created → Planned (when task is planned)
  - Planned → Assigned (when assigned to executor)
  - Assigned → In Progress (when execution starts)
  - In Progress → Completed/Failed/Cancelled/Paused (when execution ends)

### InteractionTrace
- **Fields**:
  - id (UUID): Unique identifier
  - session_id (UUID): Foreign key to Session
  - interaction_type (enum: user_input, ai_response, tool_call, plugin_call, subagent_call, task_update, context_update): Type of interaction
  - request_data (JSON): Incoming request details
  - response_data (JSON): Response details
  - timestamp (datetime): When interaction occurred
  - duration_ms (int): How long interaction took
  - success_status (boolean): Whether interaction was successful
  - trace_metadata (JSON): Additional tracing information

- **Relationships**:
  - Belongs to Session

### Configuration
- **Fields**:
  - id (UUID): Unique identifier
  - name (string): Configuration key name
  - value (JSON): Configuration value (can be string, number, boolean, or object)
  - scope (enum: global, user, session): Configuration scope level
  - user_id (UUID, optional): Foreign key to User if user-scoped
  - session_id (UUID, optional): Foreign key to Session if session-scoped
  - updated_at (datetime): When configuration was last updated
  - updated_by (UUID): User who last updated the configuration
  - encrypted (boolean): Whether the value is encrypted (for sensitive data)

- **Relationships**:
  - Optionally belongs to User (for user-scoped configs)
  - Optionally belongs to Session (for session-scoped configs)

- **Validation Rules**:
  - Global configs cannot be user-specific
  - Value type must match configuration type specification
  - Sensitive values must be encrypted

### Configuration
- **Fields**:
  - id (UUID): Unique identifier
  - name (string): Configuration key name
  - value (JSON): Configuration value (can be string, number, boolean, or object)
  - scope (enum: global, user, session): Configuration scope level
  - user_id (UUID, optional): Foreign key to User if user-scoped
  - session_id (UUID, optional): Foreign key to Session if session-scoped
  - updated_at (datetime): When configuration was last updated
  - updated_by (UUID): User who last updated the configuration
  - encrypted (boolean): Whether the value is encrypted (for sensitive data)

- **Relationships**:
  - Optionally belongs to User (for user-scoped configs)
  - Optionally belongs to Session (for session-scoped configs)

- **Validation Rules**:
  - Global configs cannot be user-specific
  - Value type must match configuration type specification
  - Sensitive values must be encrypted

## Validation Rules Summary

From functional requirements:
- FR-001: User input validation for text, image, file formats
- FR-004: Tool parameter validation before execution
- FR-008: Security validation for command execution
- FR-010: Channel authentication validation
- FR-014: Cron expression validation
- FR-016: SubAgent role validation and permission checks
- FR-017: Context compression threshold validation
- FR-019: Task cancellation permission validation
- FR-020: Configuration update validation and change approval

## State Transition Diagrams

### Session States
```
[CREATED] --> [ACTIVE] --> [PAUSED] --> [ARCHIVED]
      |           |           |           |
      v           v           v           v
   (first    (activity   (inactivity  (user req/
   interaction) timeout)    timeout)   expiration)
```

### Message Processing
```
[PENDING] --> [PROCESSING] --> [COMPLETED]
                  |              |
                  v              v
             [EXECUTING       [ERROR]
              TOOLS] -----> (needs retry/
                             user action)
```

### Task States
```
[CREATED] --> [PLANNED] --> [IN_PROGRESS] --> [COMPLETED]
    |           |              |               |
    v           v              v               v
(Creation  (Planning     (Execution     (Completion
Failure)   Confirmation)  Execution)    Validation)
```

### SubAgent States
```
[OFFLINE] --> [LOADING] --> [ACTIVE] --> [BUSY] --> [IDLE]
    |           |            |          |          |
    +-----------+------------+----------+----------+
         ^                      (Task completion)
         +----------------------+
         (Manual shutdown or timeout)
```