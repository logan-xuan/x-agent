# Quickstart Guide: x-agent2 AI Assistant System

## Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend development)
- SQLite 3.38+ (for vector search support)
- pip and npm/yarn package managers

## Environment Setup

### 1. Clone and Initialize the Project

```bash
# Clone the repository (if available)
# For now, assuming project is already available in your workspace
cd /path/to/x-agent2
```

### 2. Backend Setup

```bash
# Navigate to project root
cd /Users/hzliuxuan/Documents/qoder-workspace/x-agent2

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install backend dependencies
pip install -r requirements.txt
# If requirements.txt doesn't exist, install core dependencies:
pip install fastapi uvicorn python-multipart anthropic openai pydantic sqlalchemy sqlite-vss python-jose[cryptography] passlib[bcrypt]
```

### 3. Frontend Setup

```bash
# Navigate to frontend directory
cd src/expression/web-ui

# Install frontend dependencies
npm install
# Or if using yarn:
yarn install
```

## Configuration

### 1. Environment Variables

Create a `.env` file in the project root:

```env
# API Keys
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Database
DATABASE_URL=sqlite:///./x-agent.db

# Vector Database
VECTOR_DB_PATH=./vector_storage.sqlite

# Security
SECRET_KEY=your_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Application
DEBUG=true
LOG_LEVEL=info

# Plugin Settings
PLUGIN_DIR=./plugins
WORKSPACE_DIR=./workspace
```

### 2. Application Configuration

Create `config/app-config.yaml`:

```yaml
models:
  primary: "claude-3-5-sonnet-20241022"
  fallback: "gpt-4o"
  providers:
    - anthropic
    - openai

plugins:
  auto_load: true
  trusted_sources:
    - "./plugins"
    - "./workspace/custom-skills"
  allow_internet: false
  max_execution_time: 30

security:
  command_execution:
    allow_dangerous_commands: false
    max_concurrent_processes: 10
  file_access:
    restricted_paths:
      - "/etc"
      - "/root"
      - "/proc"
      - "/sys"
    allowed_extensions:
      - ".txt"
      - ".py"
      - ".js"
      - ".md"
      - ".json"
      - ".csv"
      - ".jpg"
      - ".png"

channels:
  web_ui:
    port: 8000
    cors_origins:
      - "http://localhost:3000"
      - "http://127.0.0.1:3000"
  dingtalk:
    enabled: false
    webhook_url: ""
  feishu:
    enabled: false
    app_id: ""
    app_secret: ""
```

## Running the System

### 1. Start the Backend Server

```bash
# Activate virtual environment
source venv/bin/activate

# Navigate to project root
cd /Users/hzliuxuan/Documents/qoder-workspace/x-agent2

# Run the backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Start the Frontend (Development)

```bash
# In a separate terminal
cd src/expression/web-ui

# Run the frontend development server
npm run dev
# Or with yarn:
yarn dev
```

### 3. Using Docker (Alternative Method)

If Docker is preferred:

```dockerfile
# Create Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Build and run
docker build -t x-agent2 .
docker run -p 8000:8000 -v $(pwd)/data:/app/data x-agent2
```

## First Steps

### 1. Access the Web Interface

Open your browser and navigate to `http://localhost:3000` to access the Web UI.

### 2. Configure Your AI Models

1. Go to Settings in the web interface
2. Add your Anthropic and/or OpenAI API keys
3. Select your preferred default model

### 3. Try Basic Functionality

- Send a text message to the AI assistant
- Try uploading an image for analysis
- Test the code writing capability
- Ask the assistant to search the web for information

### 4. Enable Advanced Features

#### Tools
The assistant can use several built-in tools:
- Web search: "Search the web for..."
- File operations: "Read/write files in my workspace"
- Code execution: "Run this Python code..."
- Command execution: "Execute this command..."

#### Memory System
The memory system is active by default. The assistant will remember:
- Previous interactions in the same session
- Your preferences and frequently used information
- Important facts shared across conversations

#### Plugins
1. Place plugin files in the `workspace/` directory
2. Restart the application or use the plugin management interface
3. Enable desired plugins through the web UI

## API Usage

The backend provides a REST API accessible at `http://localhost:8000/api/v1/`.

### Example API Calls

```bash
# Send a message
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, how can you help me?",
    "session_id": "optional-session-id"
  }'

# Get conversation history
curl http://localhost:8000/api/v1/chat/history?session_id=your-session-id

# List available plugins
curl http://localhost:8000/api/v1/plugins
```

## Troubleshooting

### Common Issues

1. **API Keys Not Working**: Ensure your API keys are correctly configured in the environment variables
2. **Database Errors**: Make sure SQLite supports vector extensions (sqlite-vss)
3. **Frontend Not Connecting**: Check CORS settings in the configuration
4. **Slow Responses**: Verify your internet connection and API key validity

### Logging

Check the application logs for detailed information:
- Backend logs are displayed in the terminal where you ran uvicorn
- For production, logs may be saved to a file based on configuration

## Next Steps

1. Customize your assistant by configuring settings
2. Install and configure plugins for enhanced functionality
3. Connect additional channels (DingTalk, Feishu, WeChat if implemented)
4. Set up scheduled tasks (Cron jobs) for automated assistance