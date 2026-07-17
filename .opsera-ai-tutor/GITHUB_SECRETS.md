# GitHub Secrets Setup Guide — AI Tutor

All secrets below must be added to your GitHub repository before running any workflow.

**Navigate to:** `https://github.com/gayathri-opsera/Ai-Tutor-Agent/settings/secrets/actions`

---

## Required Secrets

### AWS Credentials
| Secret Name | Value | Notes |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | Your AWS access key ID | IAM user with EKS, ECR, STS permissions |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret access key | Keep confidential |

### LLM API Keys
| Secret Name | Value | Notes |
|---|---|---|
| `OPENAI_API_KEY` | `sk-proj-...` | From platform.openai.com |
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` | From console.anthropic.com |
| `GROQ_API_KEY` | `gsk_...` | From console.groq.com |
| `AZURE_OPENAI_API_KEY` | (optional) | Only if using Azure OpenAI |
| `AZURE_OPENAI_ENDPOINT` | (optional) | Only if using Azure OpenAI |

### Database
| Secret Name | Value | Notes |
|---|---|---|
| `DB_HOST` | `postgres` | Use K8s service name (postgres) for in-cluster |
| `DB_PASSWORD` | Strong password | Used by PostgreSQL StatefulSet |
| `DATABASE_URL` | `postgresql://ai_tutor:<password>@postgres:5432/ai_tutor` | Full connection string |

### Cache
| Secret Name | Value | Notes |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379/0` | Use K8s service name for in-cluster Redis |

### Vector DB
| Secret Name | Value | Notes |
|---|---|---|
| `WEAVIATE_URL` | `http://weaviate:8080` | Use K8s service name for in-cluster Weaviate |

### Auth
| Secret Name | Value | Notes |
|---|---|---|
| `JWT_SECRET` | Random 64-char string | Generate: `openssl rand -hex 32` |
| `KEYCLOAK_CLIENT_SECRET` | Random string | Set same value in Keycloak client config |
| `KEYCLOAK_ADMIN_PASSWORD` | Strong password | Keycloak admin console password |

### Storage
| Secret Name | Value | Notes |
|---|---|---|
| `S3_ACCESS_KEY` | Your S3/MinIO key | For production use AWS IAM, for dev use MinIO |
| `S3_SECRET_KEY` | Your S3/MinIO secret | Keep confidential |
| `S3_ENDPOINT` | `https://s3.amazonaws.com` | For AWS S3; use MinIO URL for local dev |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/services/T.../B.../...` | Incoming webhook URL for deployment notifications; create at api.slack.com/apps |

---

## Quick Setup Script

Run this from your terminal to add all secrets at once using `gh` CLI:

```bash
# Set these variables first
OPENAI_API_KEY="sk-proj-..."
ANTHROPIC_API_KEY="sk-ant-api03-..."
GROQ_API_KEY="gsk_..."
DB_PASSWORD="$(openssl rand -hex 16)"
JWT_SECRET="$(openssl rand -hex 32)"
KEYCLOAK_ADMIN_PASSWORD="$(openssl rand -hex 16)"
KEYCLOAK_CLIENT_SECRET="$(openssl rand -hex 16)"
S3_ACCESS_KEY="your-s3-key"
S3_SECRET_KEY="your-s3-secret"
AWS_ACCESS_KEY_ID="your-aws-key-id"
AWS_SECRET_ACCESS_KEY="your-aws-secret-key"

REPO="gayathri-opsera/Ai-Tutor-Agent"

gh secret set AWS_ACCESS_KEY_ID        --body "$AWS_ACCESS_KEY_ID"        --repo "$REPO"
gh secret set AWS_SECRET_ACCESS_KEY    --body "$AWS_SECRET_ACCESS_KEY"    --repo "$REPO"
gh secret set OPENAI_API_KEY           --body "$OPENAI_API_KEY"           --repo "$REPO"
gh secret set ANTHROPIC_API_KEY        --body "$ANTHROPIC_API_KEY"        --repo "$REPO"
gh secret set GROQ_API_KEY             --body "$GROQ_API_KEY"             --repo "$REPO"
gh secret set DB_HOST                  --body "postgres"                  --repo "$REPO"
gh secret set DB_PASSWORD              --body "$DB_PASSWORD"              --repo "$REPO"
gh secret set DATABASE_URL             --body "postgresql://ai_tutor:${DB_PASSWORD}@postgres:5432/ai_tutor" --repo "$REPO"
gh secret set REDIS_URL                --body "redis://redis:6379/0"      --repo "$REPO"
gh secret set WEAVIATE_URL             --body "http://weaviate:8080"      --repo "$REPO"
gh secret set JWT_SECRET               --body "$JWT_SECRET"               --repo "$REPO"
gh secret set KEYCLOAK_CLIENT_SECRET   --body "$KEYCLOAK_CLIENT_SECRET"   --repo "$REPO"
gh secret set KEYCLOAK_ADMIN_PASSWORD  --body "$KEYCLOAK_ADMIN_PASSWORD"  --repo "$REPO"
gh secret set S3_ACCESS_KEY            --body "$S3_ACCESS_KEY"            --repo "$REPO"
gh secret set S3_SECRET_KEY            --body "$S3_SECRET_KEY"            --repo "$REPO"
gh secret set S3_ENDPOINT              --body "https://s3.amazonaws.com"  --repo "$REPO"
gh secret set AZURE_OPENAI_API_KEY     --body ""                          --repo "$REPO"
gh secret set AZURE_OPENAI_ENDPOINT    --body ""                          --repo "$REPO"
gh secret set SLACK_WEBHOOK_URL        --body "$SLACK_WEBHOOK_URL"        --repo "$REPO"

echo "✅ All secrets set"
```

---

## Deployment Order

1. **Add all GitHub secrets** (above)
2. **Run bootstrap workflow**: `Actions → 00 - Bootstrap: AI Tutor Infrastructure → Run workflow`
3. **Push code** to `main` to trigger individual service CI/CD workflows
4. **Monitor ArgoCD**: `https://argocd-usw2.agent.opsera.dev`
5. **Access app**: `https://ai-tutor-dev.agent.opsera.dev`

---

## IAM Permissions Required

The AWS IAM user needs these policies:
- `AmazonEKSFullAccess` (or scoped EKS permissions)
- `AmazonEC2ContainerRegistryFullAccess`
- `AmazonS3FullAccess` (or scoped to `ai-tutor-content` bucket)
- `IAMReadOnlyAccess` (for `sts:GetCallerIdentity`)
