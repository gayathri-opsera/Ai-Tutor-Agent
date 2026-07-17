#!/usr/bin/env python3
"""
Detect which services are affected by changed files in the current push or PR.

Reads .github/service-dependencies.json and git diff output to produce a
GitHub Actions matrix JSON of services that need to be rebuilt.

Outputs (written to $GITHUB_OUTPUT):
  matrix      — JSON object with "include" array for use in strategy.matrix
  has_changes — "true" if at least one service is affected, else "false"
"""
import json
import os
import subprocess
import sys

# Files matching these prefixes/suffixes are never relevant to service builds.
SKIP_PREFIXES = ("docs/", ".github/", "README", "LICENSE", "CHANGELOG")
SKIP_SUFFIXES = (".md", ".txt", ".rst")


def get_changed_files() -> list[str]:
    """Return list of files changed in this push or PR."""
    event = os.environ.get("GITHUB_EVENT_NAME", "push")

    if event == "pull_request":
        base_sha = os.environ.get("GITHUB_BASE_SHA", "")
        if base_sha:
            cmd = ["git", "diff", "--name-only", f"{base_sha}...HEAD"]
        else:
            cmd = ["git", "diff", "--name-only", "HEAD~1", "HEAD"]
    else:
        cmd = ["git", "diff", "--name-only", "HEAD~1", "HEAD"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        print(
            f"[detect-changes] git diff returned nothing (rc={result.returncode})",
            file=sys.stderr,
        )
        return []

    files = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
    print(f"[detect-changes] changed files ({len(files)}): {files}", file=sys.stderr)
    return files


def load_deps() -> dict:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    deps_path = os.path.join(script_dir, "..", "service-dependencies.json")
    with open(deps_path) as fh:
        return json.load(fh)


def is_skippable(path: str) -> bool:
    return any(path.startswith(p) for p in SKIP_PREFIXES) or any(
        path.endswith(s) for s in SKIP_SUFFIXES
    )


def compute_affected(changed_files: list[str], deps: dict) -> list[str]:
    """Return the set of service names that need rebuilding."""
    if not changed_files:
        return []

    relevant = [f for f in changed_files if not is_skippable(f)]
    if not relevant:
        print(
            "[detect-changes] all changes are docs/config-only — skipping builds",
            file=sys.stderr,
        )
        return []

    services_cfg: dict = deps["services"]
    shared_triggers: dict = deps.get("shared_path_triggers", {})
    lib_deps: dict = deps.get("library_dependencies", {})

    affected: set[str] = set()

    for changed in relevant:
        # 1. Direct service source path match
        for svc_name, svc in services_cfg.items():
            for src in svc.get("source_paths", []):
                if changed == src or changed.startswith(src + "/"):
                    affected.add(svc_name)

        # 2. Shared Dockerfile triggers
        for trigger_path, svc_names in shared_triggers.items():
            if changed == trigger_path or changed.startswith(trigger_path + "/"):
                affected.update(svc_names)

        # 3. Library dependency transitive rebuild
        for lib_path, svc_names in lib_deps.items():
            if changed.startswith(lib_path + "/"):
                affected.update(svc_names)

    return sorted(affected)


def build_matrix(affected_names: list[str], deps: dict) -> dict:
    """Build the GitHub Actions strategy.matrix include list."""
    services_cfg: dict = deps["services"]
    include = []
    for name in affected_names:
        if name in services_cfg:
            entry = {k: v for k, v in services_cfg[name].items() if k != "source_paths"}
            include.append(entry)
        else:
            print(
                f"[detect-changes] WARNING: affected service '{name}' not found in services config",
                file=sys.stderr,
            )
    return {"include": include}


def write_outputs(matrix: dict, has_changes: bool) -> None:
    matrix_json = json.dumps(matrix, separators=(",", ":"))
    has_str = "true" if has_changes else "false"

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"matrix={matrix_json}\n")
            fh.write(f"has_changes={has_str}\n")
    else:
        print(f"matrix={matrix_json}")
        print(f"has_changes={has_str}")


def main() -> None:
    deps = load_deps()

    force_all = "--all" in sys.argv or os.environ.get("FORCE_ALL", "").lower() == "true"

    if force_all:
        print("[detect-changes] --all flag set — rebuilding every service", file=sys.stderr)
        affected = sorted(deps["services"].keys())
    else:
        changed = get_changed_files()
        affected = compute_affected(changed, deps)

    print(
        f"[detect-changes] affected services ({len(affected)}): {affected}",
        file=sys.stderr,
    )

    matrix = build_matrix(affected, deps)
    write_outputs(matrix, has_changes=bool(affected))


if __name__ == "__main__":
    main()
