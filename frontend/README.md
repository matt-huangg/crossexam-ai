# frontend

Next.js app using static export (`output: 'export'`) — a client-side SPA.

No SSR or Next.js API routes: all dynamic work (AgentCore calls, streaming,
voice) is handled by the backend proxy in `infra/`, since this app is hosted
as static files on S3 + CloudFront.

Not yet implemented. See `../ARCHITECTURE.md` for the frontend/hosting design
and `../ROADMAP.md` for sequencing.
