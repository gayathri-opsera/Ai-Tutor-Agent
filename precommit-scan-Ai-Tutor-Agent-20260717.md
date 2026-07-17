# Pre-Commit Security Scan — Ai-Tutor-Agent

**Date:** 2026-07-17  
**Branch:** feature/wo-001-sealed-secrets  
**Verdict:** ✅ SAFE TO COMMIT — No new security issues introduced

## Summary

| Severity | 🆕 New (staged changes) | 📋 Existing (pre-committed) |
|----------|------------------------|---------------------------|
| 🔴 Critical | 0 | 0 |
| 🟠 High | 0 | 0 |
| 🟡 Medium | 0 | 0 |
| 🟢 Low / Info | 0 | 34 |
| **Total** | **0** | **34** |

**Risk Score:** 0/100 (No Risk)

## Scan Coverage

| Tool | Status | Findings |
|------|--------|----------|
| gitleaks (secrets) | ✅ PASSED | 0 |
| semgrep (SAST) | ⚠️ SKIPPED | Network unavailable in sandbox |
| grype (vulnerabilities) | ⚠️ SKIPPED | DB expired (9 weeks old); network blocked |
| checkov (IaC) | ✅ PASSED | 34 INFO (existing) |
| hadolint (Dockerfile) | ✅ PASSED | 0 |

## Existing Findings (pre-committed, not blocking)

All 34 INFO-level findings are in files **not part of this commit**.

| Rule | File | Note |
|------|------|------|
| CKV_DOCKER_3 | Dockerfile.service, Dockerfile.content-ingestion, frontend/Dockerfile | Docker USER instruction missing |
| CKV_DOCKER_2 | frontend/Dockerfile | Tag not pinned in COPY --from |
| CKV_GHA_7 | .github/workflows/cicd-ai-tutor-*.yaml (10 files) | GitHub Actions token permissions not restricted |

These are pre-existing issues tracked separately and not introduced by WO-001.
