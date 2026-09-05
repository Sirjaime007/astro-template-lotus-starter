import { defineConfig } from 'astro/config';
import lotus from '@prosefly/astro-theme-lotus';
import themeConfig from './src/theme.config.ts';

export default defineConfig({
  integrations: [lotus(themeConfig)],
});