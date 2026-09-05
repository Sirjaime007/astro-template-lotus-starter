import { defineConfig } from 'astro/config';
import lotus from '@prosefly/astro-theme-lotus';

export default defineConfig({
  integrations: [
    lotus({
      name: 'Cofiteca x Mad Diseño',
      description: 'Diseño exclusivo para el mundo del café de especialidad.',
    }),
  ],
});