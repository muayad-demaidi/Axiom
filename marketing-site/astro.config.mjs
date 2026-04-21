import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://datavisionpro.app',
  trailingSlash: 'ignore',
  integrations: [],
  server: {
    host: '0.0.0.0',
    port: 4321,
  },
  vite: {
    server: {
      allowedHosts: true,
      hmr: {
        clientPort: 443,
        protocol: 'wss',
      },
    },
    preview: {
      allowedHosts: true,
    },
  },
});
