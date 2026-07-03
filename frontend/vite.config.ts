import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// nextGen-FMS frontend port comes from the project-root .env (one level up).
// Default is 6173 so it sits alongside smart-truck's 5173 without colliding.
export default defineConfig(({ mode }) => {
  const rootEnv = loadEnv(mode, path.resolve(__dirname, '..'), '')
  const port = Number(
    rootEnv.FMS_FRONTEND_PORT ?? process.env.FMS_FRONTEND_PORT ?? 6173,
  )
  return {
    plugins: [react(), tailwindcss()],
    server: { port, strictPort: true },
    // Vite only exposes env vars prefixed with VITE_ to client code, but we
    // need the backend URL there. The .env already declares VITE_API_URL +
    // VITE_ML_API_URL — Vite picks them up automatically from the project root
    // because we loaded the parent directory above.
    envDir: path.resolve(__dirname, '..'),
  }
})
