import { defineConfig } from 'vite'

export default defineConfig({
  // Base URL for GitHub Pages (update 'pii-deidentification-project' to your repo name if different)
  // Set to '/' for root deployment or '/repo-name/' for project pages
  base: './',

  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})
