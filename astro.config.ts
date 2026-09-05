starlight({
      title: 'Tu Título',
      // AGREGA ESTAS TRES LÍNEAS:
      components: {
        Hero: './src/components/EmptyHero.astro',
      },
      // ... el resto de tus opciones siguen igual

import { defineConfig } from 'astro/config';
import lotus from '@prosefly/astro-theme-lotus';

export default defineConfig({
  integrations: [lotus()],
});
