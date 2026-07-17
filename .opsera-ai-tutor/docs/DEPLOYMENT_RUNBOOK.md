# Deployment Runbook — AI Tutor Agent

**Version:** 1.0  
**Last Updated:** 2026-07  
**Audience:** SRE, DevOps, On-Call Engineers  
**Platform:** AWS EKS (spoke cluster) + ArgoCD + GitHub Actions

---

## Table of Contents

1. [Normal Deployment Flow](#1-normal-deployment-flow)
2. [Checking Deployment Status](#2-checking-deployment-status)
3. [Rollback Scenarios](#3-rollback-scenarios)
   - [3a. Failed ArgoCD Sync](#3a-failed-argocd-sync)
   - [3b. Bad Container Image (CrashLoopBackOff)](#3b-bad-container-image-crashloopbackoff)
   - [3c. Database Migration Failure](#3c-database-migration-failure)
   - [3d. Secret Rotation Failure](#3d-secret-rotation-failure)
4. [Emergency Procedures](#4-emergency-procedures)
5. [Useful Commands Reference](#5-useful-commands-reference)

---

## 1. Normal Deployment Flow

A push to `main` triggers the CI/CD pipeline for changed services:

```
Push to main
  └── ci-matrix.yaml (detect changed services)
       └── For each affected service:
            01 - Security Scan (Gitleaks + detect-secrets)
            02 - Architectural Lint (import-linter)
            03 - Contract Validation (OpenAPI baseline)
            04 - Build Image (Docker)
            05 - Grype Vulnerability Scan
            06 - Push to ECR
            07 - Update Manifests (k8s image tag in gitops repo)
            08 - Create ArgoCD Application (if new service)
            09 - Refresh ECR Secret (pull secret in cluster)
            10 - ArgoCD Sync
            11 - Verify Deployment (kubectl wait)
            12 - Deployment Landscape (summary)
            13 - Deployment Notification (Slack)
```

**Expected duration:** 8–12 minutes per service (parallel for multiple services).

---

## 2. Checking Deployment Status

### GitHub Actions

```bash
# View recent pipeline runs
gh run list --repo gayathri-opsera/Ai-Tutor-Agent --limit 10

# Watch a specific run
gh run watch <run-id> --repo gayathri-opsera/Ai-Tutor-Agent

# View logs for a failed run
gh run view <run-id> --log-failed --repo gayathri-opsera/Ai-Tutor-Agent
```

### ArgoCD

```bash
# List all AI Tutor apps
kubectl get app -n argocd | grep ai-tutor

# Check sync status
kubectl get app opsera-ai-tutor-dev -n argocd \
  -o jsonpath='{.status.sync.status} {.status.health.status}'

# View detailed sync errors
kubectl describe app opsera-ai-tutor-dev -n argocd
```

### Kubernetes

```bash
# Set kubeconfig for spoke cluster
aws eks update-kubeconfig --name ai-tutor-spoke --region us-west-2

# Check all service pods
kubectl get pods -n ai-tutor-dev

# Check deployment rollout status
kubectl rollout status deployment/<service-name> -n ai-tutor-dev

# View recent events
kubectl get events -n ai-tutor-dev --sort-by='.lastTimestamp' | tail -30
```

---

## 3. Rollback Scenarios

### 3a. Failed ArgoCD Sync

**Symptoms:** Stage 10 (ArgoCD Sync) fails; `kubectl get app` shows `SyncFailed`.

**Step 1 — Identify the error:**
```bash
kubectl get app opsera-ai-tutor-dev -n argocd \
  -o jsonpath='{.status.operationState.message}'
```

**Step 2 — Option A: Rollback via ArgoCD (recommended):**
```bash
# Roll back to the previous successful revision
kubectl patch app opsera-ai-tutor-dev -n argocd --type merge \
  -p '{"operation":{"initiatedBy":{"username":"sre"},"sync":{"revision":"HEAD~1","prune":false}}}'

# Wait for sync
kubectl wait app opsera-ai-tutor-dev -n argocd \
  --for=jsonpath='{.status.sync.status}'=Synced --timeout=300s
```

**Step 2 — Option B: Revert the manifest commit and push:**
```bash
# In the gitops/manifests repo
git log --oneline -5
git revert HEAD --no-edit
git push origin main
# ArgoCD will auto-sync within 3 minutes
```

**Step 3 — Verify recovery:**
```bash
kubectl get pods -n ai-tutor-dev -l app=<service-name>
kubectl rollout status deployment/<service-name> -n ai-tutor-dev
```

---

### 3b. Bad Container Image (CrashLoopBackOff)

**Symptoms:** Pods in `CrashLoopBackOff` or `Error` state after deployment.

**Step 1 — Diagnose:**
```bash
kubectl get pods -n ai-tutor-dev -l app=<service-name>
kubectl logs -n ai-tutor-dev deployment/<service-name> --previous
kubectl describe pod -n ai-tutor-dev <pod-name>
```

**Step 2 — Rollback the Kubernetes deployment:**
```bash
# View rollout history
kubectl rollout history deployment/<service-name> -n ai-tutor-dev

# Roll back to the previous revision
kubectl rollout undo deployment/<service-name> -n ai-tutor-dev

# Verify
kubectl rollout status deployment/<service-name> -n ai-tutor-dev
kubectl get pods -n ai-tutor-dev -l app=<service-name>
```

**Step 3 — Pin the old ECR image tag in manifests:**
```bash
# Find the last working image tag (from GitHub Actions run history or ECR)
aws ecr describe-images --repository-name opsera/ai-tutor-<service-name> \
  --query 'sort_by(imageDetails,&imagePushedAt)[-2].imageTags' \
  --region us-west-2

# Update the manifest and push
# ArgoCD will sync the pinned image
```

**Step 4 — Revert the code change:**
```bash
git revert HEAD --no-edit   # In the application repo
git push origin main
# New CI run will rebuild and deploy the reverted code
```

---

### 3c. Database Migration Failure

**Symptoms:** Service starts but returns 500 errors; logs show `alembic` or schema errors.

**Step 1 — Identify the failed migration:**
```bash
kubectl exec -n ai-tutor-dev deployment/<service-name> -- \
  alembic history --verbose 2>&1 | tail -20

kubectl exec -n ai-tutor-dev deployment/<service-name> -- \
  alembic current
```

**Step 2 — Downgrade the migration:**
```bash
# Roll back one migration step
kubectl exec -n ai-tutor-dev deployment/<service-name> -- \
  alembic downgrade -1

# Or roll back to a specific revision
kubectl exec -n ai-tutor-dev deployment/<service-name> -- \
  alembic downgrade <revision-id>
```

**Step 3 — Roll back the application code:**
```bash
kubectl rollout undo deployment/<service-name> -n ai-tutor-dev
```

**Step 4 — Fix the migration and re-deploy:**
- Fix the Alembic migration file in the codebase
- Push to a feature branch, test in a non-production environment
- Merge to `main` to trigger CI/CD

**Important:** Never apply `alembic upgrade head` directly against production without a tested rollback plan.

---

### 3d. Secret Rotation Failure

**Symptoms:** Services return 401/403 errors after secret rotation; `OPENAI_API_KEY` or similar rotated key is rejected.

**Step 1 — Identify which secret failed:**
```bash
kubectl get secret ai-tutor-secrets -n ai-tutor-dev -o json \
  | jq '.data | keys'

# Test a specific key (e.g., OpenAI)
kubectl exec -n ai-tutor-dev deployment/llm-gateway -- \
  python3 -c "import os; print(os.environ.get('OPENAI_API_KEY', 'NOT SET')[:8])"
```

**Step 2 — Update the GitHub secret and re-trigger the bootstrap:**
```bash
# Update via gh CLI
gh secret set OPENAI_API_KEY --body "<new-key>" \
  --repo gayathri-opsera/Ai-Tutor-Agent

# Trigger the bootstrap workflow to refresh the K8s secret
gh workflow run "00 - Bootstrap: AI Tutor Infrastructure" \
  --repo gayathri-opsera/Ai-Tutor-Agent
```

**Step 3 — Force a pod restart to pick up new secret:**
```bash
kubectl rollout restart deployment/<service-name> -n ai-tutor-dev
kubectl rollout status deployment/<service-name> -n ai-tutor-dev
```

**Step 4 — Verify the SealedSecret sync (if using SealedSecrets):**
```bash
kubectl get sealedsecret -n ai-tutor-dev
kubectl get secret ai-tutor-secrets -n ai-tutor-dev
kubectl describe sealedsecret ai-tutor-secrets -n ai-tutor-dev
```

---

## 4. Emergency Procedures

### Immediate service shutdown (incident response)

```bash
# Scale down a specific service to 0 replicas
kubectl scale deployment/<service-name> --replicas=0 -n ai-tutor-dev

# Scale down ALL services (full platform shutdown)
kubectl get deployments -n ai-tutor-dev -o name | \
  xargs -I{} kubectl scale {} --replicas=0 -n ai-tutor-dev
```

### Emergency image pin (bypass ArgoCD)

Use only as a last resort — ArgoCD will revert this on next sync:

```bash
kubectl set image deployment/<service-name> \
  <service-name>=<ecr-uri>:<known-good-tag> \
  -n ai-tutor-dev

# Suspend ArgoCD auto-sync to prevent override
kubectl patch app opsera-ai-tutor-dev -n argocd \
  --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'

# Remember to re-enable auto-sync after the incident:
kubectl patch app opsera-ai-tutor-dev -n argocd \
  --type merge -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'
```

---

## 5. Useful Commands Reference

```bash
# Cluster access
aws eks update-kubeconfig --name ai-tutor-spoke --region us-west-2

# Pod status
kubectl get pods -n ai-tutor-dev -o wide

# Logs (follow)
kubectl logs -f -n ai-tutor-dev deployment/<service-name>

# Events
kubectl get events -n ai-tutor-dev --sort-by='.lastTimestamp'

# ArgoCD app tree
kubectl get app opsera-ai-tutor-dev -n argocd -o yaml | less

# ECR image tags
aws ecr list-images --repository-name opsera/ai-tutor-<service> \
  --region us-west-2 --query 'imageIds[*].imageTag' --output table

# GitHub Actions: trigger manual deploy
gh workflow run cicd-ai-tutor-<service>-dev.yaml \
  --repo gayathri-opsera/Ai-Tutor-Agent

# Force ArgoCD hard refresh
kubectl patch app opsera-ai-tutor-dev -n argocd \
  --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
```

---

*For questions or updates to this runbook, open a PR against `.opsera-ai-tutor/docs/DEPLOYMENT_RUNBOOK.md`.*
