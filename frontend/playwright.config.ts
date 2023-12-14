import { existsSync } from 'node:fs';
import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const localPython = path.resolve(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python');
const python = process.env.VERITY_PYTHON || (existsSync(localPython) ? localPython : process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'));
const pythonCommand = python.includes(' ') ? `"${python}"` : python;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  fullyParallel: false,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure', ...devices['Desktop Chrome'] },
  webServer: [
    { command: `${pythonCommand} -m uvicorn app.main:app --host 0.0.0.0 --port 8000`, cwd: '../backend', url: 'http://127.0.0.1:8000/health', reuseExistingServer: !process.env.CI, timeout: 120_000, env: { WORKER_ENABLED: 'true', DATABASE_URL: 'sqlite:///../data/e2e.db' } },
    { command: 'npm run dev -- --host 0.0.0.0', cwd: '.', url: 'http://127.0.0.1:5173', reuseExistingServer: !process.env.CI, timeout: 120_000 },
  ],
});
