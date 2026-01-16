// playwright.config.js
import { defineConfig } from '@playwright/test';

export default defineConfig({
  use: {
    baseURL: 'https://www.vertaefelungen.de/wissen/',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  retries: 1,
  timeout: 60000,
});
