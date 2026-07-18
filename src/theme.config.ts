import { defineLotusConfig } from '@prosefly/astro-theme-lotus';

export default defineLotusConfig({
  name: 'Lotus Starter',
  description: 'Documentation built with Astro Theme Lotus.',
  favicon: '/favicon.svg',
  navbar: [
    { label: 'Docs', href: '/overview/' },
    {
      label: 'GitHub',
      href: 'https://github.com/prosefly/astro-template-lotus-starter',
      external: true,
      trailingIcon: 'lucide:arrow-up-right',
    },
  ],
  socials: [
    {
      label: 'GitHub',
      href: 'https://github.com/prosefly/astro-template-lotus-starter',
      external: true,
      icon: 'github',
    },
  ],
  search: {
    provider: 'local',
  },
  source: {
    github: 'prosefly/astro-template-lotus-starter',
    branch: 'main',
  },
  editLink: true,
  sidebars: [
    {
      label: 'Start Here',
      icon: 'lucide:rocket',
      items: ['overview', 'installation', 'customization'],
    },
    {
      label: 'Guides',
      icon: 'lucide:book-open',
      items: [{ autogenerate: { directory: 'guides' } }],
    },
  ],
  footer: {
    copyright: 'Copyright © 2026.',
    sections: [
      {
        title: 'Project',
        links: [
          { label: 'Documentation', href: '/overview/' },
          {
            label: 'Source',
            href: 'https://github.com/prosefly/astro-template-lotus-starter',
            external: true,
          },
        ],
      },
      {
        title: 'Prosefly',
        links: [
          {
            label: 'Astro Theme Lotus',
            href: 'https://astro-theme-lotus.prosefly.dev',
            external: true,
          },
          {
            label: 'Astro Components',
            href: 'https://astro-components.prosefly.dev',
            external: true,
          },
        ],
      },
    ],
  },
});
