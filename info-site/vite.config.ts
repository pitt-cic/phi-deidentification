import { defineConfig } from 'vite'

export default defineConfig({
  // Base URL for GitHub Pages (update 'phi-deidentification' to your repo name if different)
  // Set to '/' for root deployment or '/repo-name/' for project pages
  base: './',

  build: {
    outDir: '../docs',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
})
