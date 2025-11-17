#!/bin/bash

# Deploy asana-brief-creation to Google Cloud Run
set -e

PROJECT_ID="emailpilot-438321"
SERVICE_NAME="asana-brief-creation"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "======================================"
echo "Deploying ${SERVICE_NAME} to Cloud Run"
echo "======================================"

# Set the project
gcloud config set project ${PROJECT_ID}

# Enable required APIs (if not already enabled)
echo "Ensuring required APIs are enabled..."
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable secretmanager.googleapis.com

# Build and push the Docker image
echo ""
echo "Building Docker image..."
cd backend
gcloud builds submit --tag ${IMAGE_NAME}
cd ..

# Deploy to Cloud Run
echo ""
echo "Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --platform managed \
  --region ${REGION} \
  --allow-unauthenticated \
  --port 8000 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10 \
  --set-env-vars "ENVIRONMENT=production,AI_PROVIDER=anthropic,AI_MODEL=claude-sonnet-4-20250514,LOG_LEVEL=INFO,DEBUG=false,ALGORITHM=HS256" \
  --set-secrets "ASANA_ACCESS_TOKEN=asana-access-token:latest,ASANA_WORKSPACE_ID=asana-workspace-id:latest,ASANA_CLIENT_ID=asana-client-id:latest,ASANA_CLIENT_SECRET=asana-client-secret:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,GOOGLE_DOCS_CREDENTIALS_PATH=google-docs-credentials:latest,SECRET_KEY=asana-webhook-secret:latest"

# Get the service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')

echo ""
echo "======================================"
echo "Deployment complete!"
echo "Service URL: ${SERVICE_URL}"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Update ASANA_OAUTH_REDIRECT_URI secret to: ${SERVICE_URL}/auth/callback"
echo "2. Test the service: ${SERVICE_URL}/api/briefs/health"
echo "3. Access the admin UI: ${SERVICE_URL}/"
