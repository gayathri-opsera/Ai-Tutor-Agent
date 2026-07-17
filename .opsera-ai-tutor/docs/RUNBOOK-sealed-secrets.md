# RUNBOOK: Sealed Secrets Management

**Service:** AI Tutor Platform  
**Scope:** Kubernetes SealedSecret lifecycle — seal, rotate, verify  
**Controller:** `sealed-secrets-controller` v0.27.1 in `kube-system`  
**Related Requirement:** REQ-008 — Secrets Management Overhaul (SOX/FFIEC)  
**Maintainers:** Platform Engineering  

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Sealing a New Secret](#sealing-a-new-secret)
4. [Rotating an Existing Secret](#rotating-an-existing-secret)
5. [Verifying Controller Health](#verifying-controller-health)
6. [Troubleshooting](#troubleshooting)
7. [Key Rotation Policy](#key-rotation-policy)
8. [Emergency Break-Glass Procedure](#emergency-break-glass-procedure)

---

## Overview

[Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) allows encrypted Kubernetes Secret manifests to be safely committed to Git. The `sealed-secrets-controller` running in `kube-system` holds a private key and decrypts `SealedSecret` CRDs into standard `Kubernetes Secrets` at runtime. ArgoCD syncs `SealedSecret` manifests from Git and the controller handles decryption.

**Why this matters for AI Tutor:**

- Eliminates `kubectl create secret generic --from-literal` at CI-time (see `00-bootstrap-infrastructure.yaml` for the deprecated block).
- Enables GitOps-compatible secret management — secrets are declared in Git, not imperatively injected.
- Satisfies SOX/FFIEC credential management controls (secrets encrypted at rest in Git; audit trail via Git history).
- Addresses ForgeScore `trust_boundaries` dimension (previously 52/100; target ≥ 80).

**Managed Secret:** `ai-tutor-secrets` in namespace `opsera-ai-tutor-dev`

**16 keys managed:**
| Category | Keys |
|----------|------|
| AI/LLM Providers | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` |
| Database | `DB_HOST`, `DB_PASSWORD`, `DATABASE_URL` |
| Cache | `REDIS_URL` |
| Vector Store | `WEAVIATE_URL`, `WEAVIATE_API_KEY` |
| Auth / Identity | `JWT_SECRET`, `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_ADMIN_PASSWORD` |
| Object Storage | `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_ENDPOINT` |

---

## Prerequisites

```bash
# Install kubeseal CLI (macOS)
brew install kubeseal

# Install kubeseal CLI (Linux)
KUBESEAL_VERSION="0.27.1"
curl -L "https://github.com/bitnami-labs/sealed-secrets/releases/download/v${KUBESEAL_VERSION}/kubeseal-${KUBESEAL_VERSION}-linux-amd64.tar.gz" | tar xz
sudo mv kubeseal /usr/local/bin/

# Verify installation
kubeseal --version
```

Ensure you have `kubectl` access to the target cluster:

```bash
# For dev environment
aws eks update-kubeconfig --name opsera-usw2-np --region us-west-2
kubectl get nodes  # should return cluster nodes
```

---

## Sealing a New Secret

Use this procedure when first provisioning the `ai-tutor-secrets` SealedSecret or when adding new secret keys.

### Step 1: Fetch the controller's public certificate

The certificate is cluster-specific. It binds the ciphertext to this cluster — sealed values cannot be decrypted by any other cluster.

```bash
# Fetch and cache the cert locally (safe to store — public key only)
kubeseal --fetch-cert \
  --controller-name=sealed-secrets-controller \
  --controller-namespace=kube-system \
  > /tmp/sealed-secrets-cert.pem

echo "✅ Certificate fetched: $(openssl x509 -noout -subject -in /tmp/sealed-secrets-cert.pem)"
```

### Step 2: Create a plain Secret manifest (DO NOT commit this file)

```bash
# Create a temporary plain-text secret manifest — NEVER commit this file.
# Add it to .gitignore immediately.
cat > /tmp/ai-tutor-secrets-plain.yaml << 'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: ai-tutor-secrets
  namespace: opsera-ai-tutor-dev
type: Opaque
stringData:
  OPENAI_API_KEY: "sk-your-openai-key-here"
  ANTHROPIC_API_KEY: "sk-ant-your-anthropic-key-here"
  GROQ_API_KEY: "gsk_your-groq-key-here"
  AZURE_OPENAI_API_KEY: "your-azure-openai-key-here"
  AZURE_OPENAI_ENDPOINT: "https://your-resource.openai.azure.com/"
  DB_HOST: "your-rds-endpoint.us-west-2.rds.amazonaws.com"
  DB_PASSWORD: "your-db-password-here"
  DATABASE_URL: "postgresql://ai_tutor_user:your-db-password@your-rds-endpoint:5432/ai_tutor_db"
  REDIS_URL: "redis://your-elasticache-endpoint:6379"
  WEAVIATE_URL: "http://weaviate.opsera-ai-tutor-dev.svc.cluster.local:8080"
  WEAVIATE_API_KEY: "your-weaviate-api-key-here"
  JWT_SECRET: "your-jwt-secret-here"
  KEYCLOAK_CLIENT_SECRET: "your-keycloak-client-secret-here"
  KEYCLOAK_ADMIN_PASSWORD: "your-keycloak-admin-password-here"
  S3_ACCESS_KEY: "your-s3-access-key-here"
  S3_SECRET_KEY: "your-s3-secret-key-here"
  S3_ENDPOINT: "https://s3.us-west-2.amazonaws.com"
EOF
```

### Step 3: Seal the secret

```bash
kubeseal \
  --format yaml \
  --cert /tmp/sealed-secrets-cert.pem \
  --controller-name=sealed-secrets-controller \
  --controller-namespace=kube-system \
  < /tmp/ai-tutor-secrets-plain.yaml \
  > .opsera-ai-tutor/k8s/base/secrets/ai-tutor-sealed-secret.yaml

echo "✅ SealedSecret written to .opsera-ai-tutor/k8s/base/secrets/ai-tutor-sealed-secret.yaml"
```

### Step 4: Update the sealed-at annotation

```bash
SEALED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Update the annotation in the file to track when it was sealed
sed -i "s/REPLACE_WITH_ISO8601_TIMESTAMP/${SEALED_AT}/" \
  .opsera-ai-tutor/k8s/base/secrets/ai-tutor-sealed-secret.yaml
```

### Step 5: Clean up plaintext and commit

```bash
# MANDATORY: remove the plaintext secret immediately
rm -f /tmp/ai-tutor-secrets-plain.yaml /tmp/sealed-secrets-cert.pem

# Commit the sealed secret to Git
git add .opsera-ai-tutor/k8s/base/secrets/ai-tutor-sealed-secret.yaml
git commit -m "chore(secrets): seal ai-tutor-secrets for opsera-ai-tutor-dev [REQ-008]"
git push
```

ArgoCD will detect the change and sync the `SealedSecret` to the cluster. The `sealed-secrets-controller` will decrypt and create the `ai-tutor-secrets` Kubernetes Secret.

---

## Rotating an Existing Secret

Use this procedure when a secret value changes (e.g., rotating an API key, changing a database password).

### Step 1: Identify which keys are changing

```bash
# View current secret keys (values are base64-encoded — do not print)
kubectl get secret ai-tutor-secrets -n opsera-ai-tutor-dev \
  -o jsonpath='{.data}' | python3 -m json.tool | grep -o '"[^"]*":' | tr -d '":' | sort
```

### Step 2: Re-seal with updated values

Repeat the [Sealing a New Secret](#sealing-a-new-secret) procedure with the new values. The `kubeseal` command overwrites the entire `SealedSecret` — all 16 keys must be present in the plaintext manifest even if only one is changing.

### Step 3: Apply and trigger pod rollout

```bash
# After pushing to Git and ArgoCD syncs automatically, OR apply manually:
kubectl apply -f .opsera-ai-tutor/k8s/base/secrets/ai-tutor-sealed-secret.yaml

# Wait for the SealedSecret to be reconciled into a Kubernetes Secret
kubectl wait --for=condition=Synced sealedsecret/ai-tutor-secrets \
  -n opsera-ai-tutor-dev --timeout=60s 2>/dev/null \
  || echo "ℹ️  Waiting for SealedSecret CRD condition support"

# Trigger a rolling restart of all pods to pick up the new secret values
kubectl rollout restart deployment -n opsera-ai-tutor-dev

# Monitor rollout progress
kubectl rollout status deployment -n opsera-ai-tutor-dev --timeout=300s
echo "✅ All deployments rolled out with new secret values"
```

### Step 4: Verify pods are healthy

```bash
kubectl get pods -n opsera-ai-tutor-dev | grep -v Running
# Should return no output if all pods are Running
```

---

## Verifying Controller Health

### Check controller is running

```bash
kubectl get deployment sealed-secrets-controller -n kube-system \
  -o jsonpath='{.status.readyReplicas}/{.status.replicas} replicas ready'
echo ""

kubectl get pods -n kube-system -l app.kubernetes.io/name=sealed-secrets \
  -o wide
```

### Check controller version

```bash
kubectl get deployment sealed-secrets-controller -n kube-system \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
echo ""
# Expected output: docker.io/bitnami/sealed-secrets-controller:v0.27.1
```

### Check sealed secret status in the namespace

```bash
kubectl get sealedsecret -n opsera-ai-tutor-dev
# Expected output:
# NAME               AGE   STATUS   SYNCED
# ai-tutor-secrets   Xm    True     True
```

### Check the decrypted secret was created

```bash
kubectl get secret ai-tutor-secrets -n opsera-ai-tutor-dev
kubectl describe secret ai-tutor-secrets -n opsera-ai-tutor-dev
# Verify 16 keys are present — values should NOT be printed
```

### Check controller logs for errors

```bash
kubectl logs -n kube-system \
  -l app.kubernetes.io/name=sealed-secrets \
  --tail=50 | grep -i "error\|warn\|unseal"
```

---

## Troubleshooting

### `no key could decrypt secret` error

The SealedSecret was encrypted with a key that the controller no longer has. This happens if:
- The controller was redeployed and lost its key (keys should persist via a Kubernetes Secret in `kube-system`)
- The SealedSecret was sealed against a different cluster's certificate

**Fix:** Re-seal the secret using the current cluster's certificate per [Sealing a New Secret](#sealing-a-new-secret).

### `cannot unseal: incorrect namespace` error

The `encryptedData` values were sealed for a different namespace than where the `SealedSecret` was applied.

**Fix:** Ensure the `namespace` in the `SealedSecret` metadata matches the namespace used when running `kubeseal`. Re-seal if needed.

### ArgoCD shows `OutOfSync` on SealedSecret

ArgoCD may detect diff between the sealed secret spec and the live object (e.g., if the controller adds annotations). Add the following to the ArgoCD Application to ignore these fields:

```yaml
spec:
  ignoreDifferences:
    - group: bitnami.com
      kind: SealedSecret
      jsonPointers:
        - /metadata/creationTimestamp
```

### Controller is not running after cluster upgrade

Check if the `sealed-secrets-controller` Deployment exists and the pod is scheduled:

```bash
kubectl describe deployment sealed-secrets-controller -n kube-system
kubectl get events -n kube-system --field-selector reason=Failed | tail -10
```

Re-run the bootstrap workflow's "Install Sealed Secrets Controller" step to reinstall.

---

## Key Rotation Policy

The Sealed Secrets controller auto-generates a new TLS keypair every 30 days (configurable via `keyRenewPeriod: 720h` in `values.yaml`). Old keys are **retained** — the controller keeps all historical private keys so previously-sealed secrets continue to decrypt.

**What this means for operations:**
- You do NOT need to re-seal secrets on every key rotation.
- Re-sealing periodically (e.g., quarterly) with the latest cert is a security best practice.
- If you delete the `sealed-secrets-controller` Namespace or Deployment's key Secret (`sealed-secrets-key` in `kube-system`), ALL sealed secrets become permanently unreadable. **Back up this secret.**

### Back up the controller's private key

```bash
# Backup the controller's private key Secret — store in a secure vault.
# NEVER commit this to Git.
kubectl get secret -n kube-system \
  -l sealedsecrets.bitnami.com/sealed-secrets-key=active \
  -o yaml > /secure/offline-backup/sealed-secrets-key-$(date +%Y%m%d).yaml

echo "⚠️  Store this file in a secure offline location (e.g., AWS Secrets Manager, 1Password)"
```

---

## Emergency Break-Glass Procedure

If the Sealed Secrets controller is unavailable and services need secrets immediately:

1. Restore the controller's private key from backup (see [Key Rotation Policy](#key-rotation-policy)).
2. If the key is unrecoverable, re-seal all secrets from scratch per [Sealing a New Secret](#sealing-a-new-secret) after recovering the controller.
3. While the controller is being restored, temporarily use the deprecated `kubectl create secret generic` bootstrap step in `00-bootstrap-infrastructure.yaml` to inject secrets directly.
4. Once the controller is healthy, re-seal and remove the temporary plaintext injection.

> **Escalation:** Notify the Platform Engineering lead immediately. Log the incident in the audit trail. Rotate all affected secret values after recovery.
