#!/usr/bin/env bash
# ============================================================================
# deploy.sh — End-to-end AWS deployment for Travel Insurance RAG Backend
#
# Prerequisites:
#   1. AWS CLI installed and configured (`aws configure`)
#   2. AWS CDK installed (`npm install -g aws-cdk`)
#   3. Docker installed and running
#   4. GitHub OIDC role ARN in env: AWS_ROLE_ARN (for CI/CD, optional locally)
#
# Usage:
#   chmod +x scripts/deploy.sh
#   ./scripts/deploy.sh                  # deploy dev stack
#   ./scripts/deploy.sh --env staging    # deploy staging stack
#   ./scripts/deploy.sh --with-alb       # deploy with an Application Load Balancer
#   ./scripts/deploy.sh --skip-secrets   # skip Secrets Manager population step
# ============================================================================

set -euo pipefail

# Resolve the project root (works regardless of where script is called from)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------
check_cmd() { command -v "$1" &>/dev/null || { echo "ERROR: '$1' not found. $2"; exit 1; }; }
check_cmd aws    "Install: https://aws.amazon.com/cli/ then run 'aws configure'"
check_cmd docker "Install: https://docs.docker.com/desktop/"
check_cmd uv     "Install: https://docs.astral.sh/uv/getting-started/installation/"
# CDK resolved below — either global cdk or npx

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
ENV="dev"
WITH_ALB="false"
SKIP_SECRETS="false"
AWS_REGION="${AWS_REGION:-us-east-1}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Resolve CDK command (global install preferred, fall back to npx)
if command -v cdk &>/dev/null; then
    CDK="cdk"
else
    CDK="npx cdk"
fi

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env)        ENV="$2"; shift 2 ;;
        --with-alb)   WITH_ALB="true"; shift ;;
        --skip-secrets) SKIP_SECRETS="true"; shift ;;
        --tag)        IMAGE_TAG="$2"; shift 2 ;;
        *)            echo "Unknown argument: $1"; exit 1 ;;
    esac
done

PREFIX="${ENV}-travel-insurance"
CDK_STACK_NAME="TravelInsurance-${ENV}"
ECR_REPO="${PREFIX}-backend"
ECS_CLUSTER="${PREFIX}-cluster"
ECS_SERVICE="${PREFIX}-service"

echo "============================================================"
echo " Travel Insurance RAG Backend — Deployment"
echo " Environment : ${ENV}"
echo " Region      : ${AWS_REGION}"
echo " ALB         : ${WITH_ALB}"
echo " Image Tag   : ${IMAGE_TAG}"
echo "============================================================"

# ===========================================================================
# Step 1: Bootstrap CDK (first-time only)
# ===========================================================================
echo ""
echo "[1/7] Bootstrapping CDK environment..."
uv pip install --system -q -r "$PROJECT_ROOT/infra/requirements.txt"

CDK_BOOTSTRAPPED=$(aws cloudformation describe-stacks \
    --stack-name CDKToolkit \
    --region "$AWS_REGION" \
    --query 'Stacks[0].StackName' \
    --output text 2>/dev/null || echo "")

if [ -z "$CDK_BOOTSTRAPPED" ]; then
    echo "  CDK Toolkit stack not found. Bootstrapping..."
    pushd "$PROJECT_ROOT/infra" > /dev/null
    $CDK bootstrap "aws://$(aws sts get-caller-identity --query Account --output text)/${AWS_REGION}"
    popd > /dev/null
else
    echo "  CDK Toolkit already bootstrapped."
fi

# ===========================================================================
# Step 2: Deploy infrastructure (CDK)
# ===========================================================================
echo ""
echo "[2/7] Deploying infrastructure via CDK..."

ALB_CONTEXT=""
if [ "$WITH_ALB" = "true" ]; then
    ALB_CONTEXT="-c enable_alb=true"
fi

pushd "$PROJECT_ROOT/infra" > /dev/null
$CDK deploy "$CDK_STACK_NAME" \
    --require-approval never \
    -c env="$ENV" \
    $ALB_CONTEXT
popd > /dev/null

# Collect outputs
S3_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name "$CDK_STACK_NAME" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='S3BucketName'].OutputValue" \
    --output text)

SECRET_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$CDK_STACK_NAME" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='SecretsManagerArn'].OutputValue" \
    --output text)

ECR_URI=$(aws cloudformation describe-stacks \
    --stack-name "$CDK_STACK_NAME" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='ECRRepositoryUri'].OutputValue" \
    --output text)

DDB_TABLE=$(aws cloudformation describe-stacks \
    --stack-name "$CDK_STACK_NAME" \
    --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='DynamoDBTableName'].OutputValue" \
    --output text)

echo "  S3 Bucket     : ${S3_BUCKET}"
echo "  DynamoDB Table: ${DDB_TABLE}"
echo "  ECR URI       : ${ECR_URI}"

# ===========================================================================
# Step 3: Populate Secrets Manager
# ===========================================================================
echo ""
echo "[3/7] Populating Secrets Manager..."

if [ "$SKIP_SECRETS" = "true" ]; then
    echo "  Skipped (--skip-secrets flag set)."
else
    # Check if secret is already populated
    EXISTING=$(aws secretsmanager describe-secret \
        --secret-id "${PREFIX}/api-keys" \
        --region "$AWS_REGION" \
        --query 'CreatedDate' \
        --output text 2>/dev/null || echo "")

    echo "  Secret ARN: ${SECRET_ARN}"
    echo ""
    echo "  Populate the secret with the following JSON structure:"
    echo "  {"
    echo "    \"GEMINI_API_KEY\": \"your-gemini-key\","
    echo "    \"PINECONE_API_KEY\": \"your-pinecone-key\","
    echo "    \"PINECONE_INDEX_NAME\": \"blue-cross-travel\""
    echo "  }"
    echo ""
    echo "  Run this command to set it:"
    echo "  aws secretsmanager put-secret-value \\"
    echo "    --secret-id ${PREFIX}/api-keys \\"
    echo "    --region ${AWS_REGION} \\"
    echo "    --secret-string '{\"GEMINI_API_KEY\":\"...\",\"PINECONE_API_KEY\":\"...\",\"PINECONE_INDEX_NAME\":\"blue-cross-travel\"}'"
fi

# ===========================================================================
# Step 4: Build & push Docker image
# ===========================================================================
echo ""
echo "[4/7] Building & pushing Docker image..."
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$ECR_URI"

docker build --platform linux/amd64 -t "${ECR_REPO}:${IMAGE_TAG}" "$PROJECT_ROOT"
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_URI}:latest"
docker push "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:latest"

echo "  Image pushed: ${ECR_URI}:${IMAGE_TAG}"

# ===========================================================================
# Step 5: Deploy ECS service (force new deployment)
# ===========================================================================
echo ""
echo "[5/7] Triggering ECS service deployment..."

# CDK generates service names with random suffixes — resolve dynamically
ECS_SERVICE_ARN=$(aws ecs list-services \
    --cluster "$ECS_CLUSTER" \
    --region "$AWS_REGION" \
    --query "serviceArns[0]" \
    --output text)

if [ -z "$ECS_SERVICE_ARN" ] || [ "$ECS_SERVICE_ARN" = "None" ]; then
    echo "  ERROR: No services found in cluster ${ECS_CLUSTER}."
    exit 1
fi

ECS_SERVICE_NAME=$(basename "$ECS_SERVICE_ARN")
echo "  Resolved service: ${ECS_SERVICE_NAME}"

aws ecs update-service \
    --cluster "$ECS_CLUSTER" \
    --service "$ECS_SERVICE_NAME" \
    --force-new-deployment \
    --region "$AWS_REGION" \
    --no-cli-pager

# ===========================================================================
# Step 6: Wait for service to stabilize
# ===========================================================================
echo ""
echo "[6/7] Waiting for ECS service to stabilize (this may take 2-5 minutes)..."
if aws ecs wait services-stable \
    --cluster "$ECS_CLUSTER" \
    --services "$ECS_SERVICE_NAME" \
    --region "$AWS_REGION"; then
    echo "  Service is stable."
else
    echo "  WARNING: Service did not stabilize within the wait period."
    echo "  Check CloudWatch logs: /ecs/${PREFIX}"
fi

# ===========================================================================
# Step 7: Health check
# ===========================================================================
echo ""
echo "[7/7] Running health check..."

TASK_ARN=$(aws ecs list-tasks \
    --cluster "$ECS_CLUSTER" \
    --service-name "$ECS_SERVICE_NAME" \
    --region "$AWS_REGION" \
    --query 'taskArns[0]' \
    --output text)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
    echo "  ERROR: No running tasks found for service ${ECS_SERVICE}."
    exit 1
fi

ENI_ID=$(aws ecs describe-tasks \
    --cluster "$ECS_CLUSTER" \
    --tasks "$TASK_ARN" \
    --region "$AWS_REGION" \
    --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
    --output text)

PUBLIC_IP=$(aws ec2 describe-network-interfaces \
    --network-interface-ids "$ENI_ID" \
    --region "$AWS_REGION" \
    --query 'NetworkInterfaces[0].Association.PublicIp' \
    --output text)

echo "  Task public IP: ${PUBLIC_IP}"

for i in $(seq 1 10); do
    STATUS=$(curl -s -o /dev/null -w '%{http_code}' "http://${PUBLIC_IP}:8000/api/health" || echo "000")
    if [ "$STATUS" = "200" ]; then
        echo ""
        echo "============================================================"
        echo " DEPLOYMENT SUCCESSFUL"
        echo "============================================================"
        echo " Health check : PASSED (HTTP 200)"
        echo " Public IP    : ${PUBLIC_IP}"
        echo " API base URL : http://${PUBLIC_IP}:8000"
        echo ""
        echo " Next steps:"
        echo "  1. Upload policy PDFs to S3:"
        echo "     aws s3 cp public/blue_cross_policy.pdf s3://${S3_BUCKET}/policies/"
        echo ""
        echo "  2. Run ingestion pipeline:"
        echo "     python scripts/ingest.py --bucket ${S3_BUCKET} --prefix policies/"
        echo ""
        echo "  3. Update frontend CORS origin to: http://${PUBLIC_IP}:8000"
        echo "============================================================"
        exit 0
    fi
    echo "  Attempt ${i}/10: HTTP ${STATUS} — retrying..."
    sleep 6
done

echo "  Health check FAILED after 10 attempts."
echo "  Check logs: aws logs tail /ecs/${PREFIX} --region ${AWS_REGION}"
exit 1
