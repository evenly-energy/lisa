---
name: review-ticket
description: >-
  Review and validate a Linear ticket with its subtasks against the codebase.
  Identifies issues, suggests improvements, and outputs diff reports when making changes.
  Use for ticket refinement and validation.
user-invocable: true
allowed-tools: >-
  Bash, Task, Glob, Grep, Read, Skill
---

# Review Ticket

Deeply analyze a Linear ticket and its subtasks for correctness, completeness,
and alignment with the codebase.

## Triggers

Activate when user says:
- "review {ticket_prefix}-123"
- "validate {ticket_prefix}-45"
- "check ticket {ticket_prefix}-67"
- "analyze {ticket_prefix}-89 for issues"

## Linear API Access

Lisa stores Linear auth at `~/.config/lisa/auth.json` (OAuth token) or via
`LINEAR_API_KEY` env var. Use Bash with curl to query the Linear GraphQL API.

### Auth helper

```bash
# Get auth header: prefer LINEAR_API_KEY, fall back to lisa OAuth token
if [ -n "$LINEAR_API_KEY" ]; then
  AUTH="$LINEAR_API_KEY"
else
  AUTH="Bearer $(python3 -c "import json; print(json.load(open('$HOME/.config/lisa/auth.json'))['access_token'])")"
fi
```

### Fetch a ticket with subtasks

```bash
curl -s https://api.linear.app/graphql \
  -H "Authorization: $AUTH" \
  -H "Content-Type: application/json" \
  -d '{"query": "query($id: String!) { issue(id: $id) { id identifier title description url children { nodes { id identifier title description state { name } } } } }", "variables": {"id": "TICKET_ID"}}'
```

### Update a ticket

```bash
curl -s https://api.linear.app/graphql \
  -H "Authorization: $AUTH" \
  -H "Content-Type: application/json" \
  -d '{"query": "mutation($id: String!, $input: IssueUpdateInput!) { issueUpdate(id: $id, input: $input) { success } }", "variables": {"id": "ISSUE_UUID", "input": {"description": "new description"}}}'
```

### Create a subtask

```bash
curl -s https://api.linear.app/graphql \
  -H "Authorization: $AUTH" \
  -H "Content-Type: application/json" \
  -d '{"query": "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { identifier } } }", "variables": {"input": {"title": "Subtask title", "description": "Details", "parentId": "PARENT_UUID", "teamId": "TEAM_UUID"}}}'
```


## Process

### 1. Fetch Ticket Hierarchy

Use the curl commands above to fetch the ticket and all subtasks.
Extract the ticket identifier from user input (e.g. "{ticket_prefix}-123").
For each subtask, fetch full details if the description appears truncated.

### 2. Explore Codebase (REQUIRED)

**You MUST use the Explore agent before producing any analysis.** This is not optional.

Use Task tool with `subagent_type: Explore` to understand:
- Existing patterns and conventions in the codebase
- Related entities, services, events
- Database migrations and schema
- API client methods and existing integrations

Focus exploration on ticket content:
- Event names: search for existing event classes and naming patterns
- Entity fields: find existing entity patterns and conventions
- API endpoints: explore controller patterns and routes
- Database schema: check migration patterns and naming

Example exploration prompt:
```
"Explore the codebase for patterns related to [ticket domain]. Find:
existing events, entities, services, and API patterns. Thoroughness: medium"
```

### 3. Review Documentation

Search the repository for documentation relevant to the ticket's domain:
- ADRs and architecture decision records
- API specs and OpenAPI schemas
- READMEs in related modules or directories
- `.claude/skills/` that document API contracts or domain conventions

Use Glob to find docs (`docs/**/*.md`, `**/README.md`, `**/openapi.*`,
`**/ADR*`) and Read to review relevant ones. Validate ticket descriptions
against documented contracts, field names, and integration patterns.

### 4. Validate Correctness

Check for:

**Naming Consistency**
- Event names match existing events in the codebase
- Entity naming follows project conventions
- Endpoint paths follow existing route patterns

**Technical Accuracy**
- API payloads match actual API contracts (check JSON casing, field names)
- Database fields align with entity conventions
- Referenced methods/classes actually exist in the codebase

**Scope Alignment**
- Subtasks cover all parent ticket DoD items
- No overlap or gaps between subtasks
- Clear boundaries between subtasks

**Architecture Fit**
- Follows module structure (public API vs internal)
- Event-driven patterns used correctly where applicable
- Proper separation of concerns

### 5. Validate Implementability

Check that the ticket is actionable by an autonomous implementer:

**Context Sufficiency**
- Description contains enough detail for someone with no prior context
- No references to external conversations ("as discussed", Slack links) without inline summary
- External resources (Figma, docs) are described in text, not just linked
- Domain terms are explained or match codebase naming

**Definition of Done**
- Clear, concrete acceptance criteria (not vague goals like "improve X")
- Each criterion is testable — can be verified by running tests or checking behavior
- Expected inputs/outputs or behavior described where applicable

**Subtask Granularity**
- Each subtask is a single focused change (one file area, one concern)
- Not too large (Lisa loses track) or too small (overhead per subtask)
- Good size: ~1 function/class/endpoint per subtask
- Flag subtasks that try to do multiple unrelated things

**Dependency Order**
- Subtask blocking relations are correct (foundations before consumers)
- Data model/schema changes come before business logic
- Business logic comes before API/UI layers
- No circular dependencies

**Testability**
- Ticket specifies how to verify the implementation
- Test commands or expected test behavior described
- If no tests exist yet, subtask for adding tests is included

### 6. Output Analysis Report

Present findings in structured format:

```markdown
## Ticket Review: {ticket_prefix}-XXX - [Title]

### Sources Consulted
- **Codebase**: [areas explored, key files found]
- **Documentation**: [skills loaded, if any]

### Summary
[1-2 sentence overview]

### Subtasks
| ID | Title | Status |
|----|-------|--------|
| {ticket_prefix}-XX | ... | Backlog |

### Correctness
- [item] - [status] [details]

### Implementability
- [ ] Context is self-contained (no external-only references)
- [ ] Clear definition of done with testable criteria
- [ ] Subtasks are right-sized (single focused change each)
- [ ] Dependency order is correct
- [ ] Verification approach is specified

### Issues Found
1. **[Category]**: [description]
   - Current: [what ticket says]
   - Should be: [correct version]

### Potential Improvements
1. [suggestion]

### Missing Items
1. [gap identified]
```

### 7. Apply Changes (if requested)

When user approves changes, use the curl mutation commands above to:

1. Update ticket descriptions
2. Create new subtasks
3. Output diff report after all changes

## Diff Report Format

After making changes, output a diff view:

```markdown
## Changes Made

### {ticket_prefix}-XX (Title)
```diff
**Section:**
-Old text that was removed
+New text that was added

Unchanged context line
```

### NEW: {ticket_prefix}-YY (New Subtask Title)
Created subtask for [purpose]
```

## Tips

- Check for JSON casing mismatches (snake_case vs camelCase vs PascalCase)
- Verify event names against existing event classes in the codebase
- Cross-reference entity fields with existing entities
- Look for missing security/observability considerations
- Ensure idempotency is addressed for webhooks/events
