const path = require("path");

const rootDir = __dirname;

module.exports = {
  apps: [
    {
      name: "x-agent-backend",
      cwd: rootDir,
      script: "./scripts/pm2-backend.sh",
      interpreter: "/bin/bash",
      exec_mode: "fork",
      instances: 1,
      watch: false,
      autorestart: true,
      min_uptime: "10s",
      max_restarts: 10,
      restart_delay: 3000,
      kill_timeout: 10000,
      out_file: path.join(rootDir, "backend/logs/pm2-backend.out.log"),
      error_file: path.join(rootDir, "backend/logs/pm2-backend.err.log"),
      merge_logs: true,
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
      },
      env_production: {
        APP_ENV: "production",
      },
      env_development: {
        APP_ENV: "development",
      },
    },
    {
      name: "x-agent-frontend",
      cwd: rootDir,
      script: "./scripts/pm2-frontend.sh",
      interpreter: "/bin/bash",
      exec_mode: "fork",
      instances: 1,
      watch: false,
      autorestart: true,
      min_uptime: "10s",
      max_restarts: 10,
      restart_delay: 3000,
      kill_timeout: 15000,
      out_file: path.join(rootDir, "frontend/pm2-frontend.out.log"),
      error_file: path.join(rootDir, "frontend/pm2-frontend.err.log"),
      merge_logs: true,
      time: true,
      env: {
        PM2_FRONTEND_HOST: "0.0.0.0",
      },
      env_production: {
        NODE_ENV: "production",
        PM2_FRONTEND_SERVE_MODE: "preview",
      },
      env_development: {
        NODE_ENV: "development",
        PM2_FRONTEND_SERVE_MODE: "dev",
      },
    },
  ],
};
