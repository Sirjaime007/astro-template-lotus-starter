import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  integrations: [
    starlight({
      title: 'Cofiteca x Mad Diseño',
      components: {
        Hero: './src/components/EmptyHero.astro',
      },
    }),
  ],
});