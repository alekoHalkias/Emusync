# Plan: #638 Fix release workflow failing on electron-builder publish

Issue: #638
Branch: feature/638-release-publish-fix
PR: none
Status: implemented
Fix attempts: 0

## Goal
Build jobs produce artifacts without publishing, and the release job attaches installers plus electron-updater metadata.

## Design Alignment
- **Backend Pattern**: none; CI/build config only. The workflow already uploads artifacts and a single release job publishes them.
- **Recommendations**: none

## Steps
- [x] 1. Stop electron-builder from publishing during the build.
  - Files: src/gui/package.json
  - Reuses: existing `dist` script
  - New: none; add `--publish never` to the `electron-builder` call (builder still writes latest*.yml with a github publish config).
- [x] 2. Upload the update metadata with the installers.
  - Files: .github/workflows/release.yml
  - Reuses: existing upload-artifact steps and the release job's `files: dist/*`
  - New: none; extend the artifact `path` to a multi-line list adding `src/gui/dist/latest-linux.yml` (Linux) and `src/gui/dist/latest.yml` (Windows).
- [x] 3. Tests: none needed - CI-only change, verified by pushing a tag. No Python code touched.
- [x] 4. Docs: CLAUDE.md "Releases" line: note that release assets include `latest*.yml` for electron-updater.

## Testing
- **Test File**: none; no Python or Electron logic changes, no JS test runner for build config.
- **Test Cases**:
  - Workflow/YAML validity: `python3 -c yaml.safe_load` on release.yml.
  - Real check: push the tag and confirm the Release run succeeds and the release holds AppImage, exe, latest.yml, latest-linux.yml.
- **Edge Cases**:
  - `--publish never` still emits latest*.yml: verify by checking the Linux run's artifact contents.
- **Integration Points**:
  - electron-updater reads latest*.yml from the release assets.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Re-tagging v0.7.0 (done after merge), code signing, update-channel configuration.

## Log
