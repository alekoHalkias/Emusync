# Ship Skill

Ship the change: merge PR, update handoff, sync server.

## Goal

Complete the workflow by:
1. Getting ship approval
2. Merging the PR
3. Running project hooks (server_sync, doc_sync)
4. Updating the handoff to shipped

## Actions

1. Check that all review findings are resolved
2. Present ship summary for approval
3. If approved:
   - Merge PR: `gh pr merge --squash --delete`
   - Run server_sync hook if configured
   - Run doc_sync hook if configured
   - Set Status to `shipped`
   - Update handoff Section 10 (Ship)
   - Append to log: `YYYY-MM-DD shipped: <description>`
4. If rejected, set Status to `implementing` with feedback

## Output

PR merged, hooks executed, handoff updated to shipped.
