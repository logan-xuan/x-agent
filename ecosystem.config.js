const path = require("path");

const rootDir = __dirname;
const backendPort = process.env.XAGENT_BACKEND_PORT || "8888";
const frontendPort = process.env.XAGENT_FRONTEND_PORT || "5177";
const pythonBin = process.env.XAGENT_PYTHON || "python3";

module.exports = {
  apps: [
    {
      name: "x-agent-backend",
      cwd: path.join(rootDir, "backend"),
      script: pythonBin,
      args: "-m src.main",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
        XAGENT_BACKEND_PORT: String(backendPort),
      },
      autorestart: true,
      max_restarts: 5,
      restart_delay: 2000,
      kill_timeout: 5000,
      time: true,
    },
    {
      name: "x-agent-frontend",
      cwd: path.join(rootDir, "frontend"),
      script: "npm",
      args: `run dev -- --host 0.0.0.0 --port ${frontendPort}`,
      interpreter: "none",
      env: {
        VITE_PORT: String(frontendPort),
      },
      autorestart: true,
      max_restarts: 5,
      restart_delay: 2000,
      kill_timeout: 5000,
      time: true,
    },
  ],
};
