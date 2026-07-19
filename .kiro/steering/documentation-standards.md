# Confluence Documentation Standards

## Purpose

You are responsible for generating and publishing comprehensive documentation to Confluence from code repositories.

The documentation is intended to serve as an Operations Knowledge Base that enables Development and Operations teams to quickly identify component ownership, data lineage, scheduling, dependencies, and troubleshooting information.

The primary goal is operational usefulness rather than simply documenting code objects.

---

## Working Directory

Always execute publisher scripts from the `publishers/` directory of this project.

This ensures:
- `.env` is loaded correctly
- Python dependencies resolve correctly
- Relative paths resolve correctly

---

## Repository Base Path

<!-- CUSTOMIZE: Set your local repository root path -->
Repositories are located under:

```
/path/to/your/repos/
```

---

## Supported Platforms

<!-- CUSTOMIZE: Add your platforms/factories here -->

| Platform | Repository | Default Branch | Publisher Script |
|----------|------------|----------------|------------------|
| Platform A (Main) | your-repo-a | main | publish_platform_a.py |
| Platform A (BC) | your-repo-a-bc | main | publish_platform_a_bc.py |
| Platform B | your-repo-b | main | publish_platform_b.py |
| Platform C | your-repo-c | release | publish_platform_c.py |

---

## Platform Selection

Always ask the user which platform or platforms should be processed.

Accept inputs such as:
- ALL
- Platform A
- Platform B
- Platform C

---

## Branch Selection

After platform selection:

Show the default branch for each selected repository.

Allow the user to:
- Accept the default branch
- Override with another branch

Never assume a branch without confirmation.

---

## Execution Workflow

Always execute in this order:

1. Ask which platform/platforms to process.
2. Ask which Git branch should be used.
3. Confirm:
   - Platform
   - Repository
   - Branch
4. Checkout the selected branch.
5. Execute git pull.
6. If git pull fails:
   - Report the failure.
   - Continue using the local repository.
   - Do not abort.
7. Execute the appropriate publisher script.
8. Publish documentation to Confluence.
9. Report:
   - Success
   - Failures
   - Warnings
   - Documentation statistics

If ALL is selected, execute all publisher scripts sequentially.

---

## Security

Never expose secrets from the `.env` file.

Examples include:
- CONFLUENCE_PAT
- CONFLUENCE_BASE_URL
- SPACE
- Any API keys or tokens

---

## Scan Scope (Azure Data Factory)

When processing ADF repositories, analyze every artifact:

- Pipelines
- Activities (Copy, Execute Pipeline, Stored Procedure, Script, ForEach, If, Switch, etc.)
- Datasets
- Linked Services
- Triggers
- Integration Runtimes
- Global Parameters

---

## Scan Scope (Azure Functions)

When processing Azure Functions repositories, analyze:

- function.json (bindings, triggers, inputs, outputs)
- host.json (global configuration)
- local.settings.json structure (environment variables)
- Code files for dependency identification

---

## Scan Scope (Kubernetes)

When processing Kubernetes repositories, analyze:

- Deployments
- CronJobs
- Services
- ConfigMaps
- Secrets (names only, never values)
- Ingress definitions

---

## Pipeline / Component Documentation

Document for every component:

- Name
- Folder / Namespace
- Description
- Git Repository
- Git Branch
- Parameters / Configuration
- Trigger(s) / Schedule
- Retry Policy
- Timeout
- Dependencies (parent/child)
- Execution Order

---

## Data Lineage (ADF-Specific)

Extract complete lineage for Copy activities:

```
Source Technology → Source Linked Service → Source Dataset
↓
ADF Pipeline (Activity, Integration Runtime)
↓
Intermediate Storage (ADLS / Blob)
↓
Target Linked Service → Target Dataset → Target Table
```

Recognize enterprise ingestion patterns:
- SQL Server → ADF → ADLS → COPY INTO Snowflake
- PostgreSQL → ADF → ADLS → Snowpipe → Snowflake
- API → ADF → Blob → Processing

Never omit intermediate storage when it exists.

---

## Parameter Resolution

Trace parameters across:
- Trigger → Pipeline → Execute Pipeline → Dataset → Linked Service → Expressions

Resolve values whenever possible.

If runtime resolution is required, document:
```
Resolved at runtime from parameter <parameter_name>
```

Never fabricate values. Unknown values must be marked `N/A`.

---

## Operations Summary

Generate for every pipeline/component:

- Purpose
- Business Domain
- Source System
- Intermediate Storage
- Target System
- Trigger Frequency
- Expected Refresh Frequency
- Critical Dependencies
- Failure Impact
- Recommended Debugging Starting Point

---

## Quality Rules

- Never fabricate values
- Mark unknown values as "N/A"
- Always trace complete lineage paths
- Document all triggers with timezone
- Identify parent/child pipeline relationships
- Count active vs. stopped triggers
- Include timestamp of documentation generation
