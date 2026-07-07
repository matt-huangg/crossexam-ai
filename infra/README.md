# infra

Deployment configuration for:

- S3 + CloudFront hosting of the static-export frontend
- The backend proxy (Lambda or similar) that holds AWS credentials, signs
  SigV4 requests to Amazon Bedrock AgentCore Runtime, and streams responses
  back to the browser
- Amazon Bedrock AgentCore Runtime deployment config for the `backend/`
  LangGraph app

Not yet implemented. See `../ARCHITECTURE.md` for the hosting/infra design
and `../ROADMAP.md` for sequencing.
