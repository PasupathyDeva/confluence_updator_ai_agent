# Confluence Documentation Agent

An AI-powered agent that automatically generates and publishes Operations Knowledge Base documentation to Confluence by reading your code repositories.

Built to run inside [Kiro CLI](https://kiro.dev) — Amazon's AI-powered development assistant.

---

## What It Does

Point this agent at any Azure Data Factory Git repository and it will:

1. **Parse** every pipeline, dataset, linked service, trigger, and integration runtime
2. **Extract** complete end-to-end data lineage (Source → ADF → Intermediate Storage → Target)
3. **Generate** structured Confluence HTML with visual lineage diagrams
4. **Publish** directly to Confluence via REST API

The result is a fully documented Operations Knowledge Base page — auto-generated, always in sync with your code.

---

## Architecture

```
┌──────────────┐     ┌───────────────────┐     ┌─────────────────┐     ┌──────────────┐
│   You        │────▶│    Kiro CLI       │────▶│  Doc Agent      │────▶│  Publisher    │
│  (Terminal)  │     │   (AI Runtime)    │     │  (Steering AI)  │     │  (Python)    │
└──────────────┘     └───────────────────┘     └─────────────────┘     └──────┬───────┘
                                                                               │
                     ┌───────────────────┐     ┌─────────────────┐             │
                     │  Confluence       │◀────│  REST API       │◀────────────┘
                     │  (Wiki Page)      │     │  (HTML Publish) │
                     └───────────────────┘     └─────────────────┘
```

---

## Project Structure

```
confluence-doc-agent/
├── .kiro/
│   ├── agents/
│   │   └── confluence-doc-agent.json    # Agent definition for Kiro CLI
│   └── steering/
│       └── documentation-standards.md   # AI steering document (rules & behavior)
├── publishers/
│   ├── adf_kb_common.py                 # Core engine — parsing, HTML gen, publishing
│   ├── publish_platform_a.py            # Example: Platform A publisher (thin wrapper)
│   └── publish_platform_b.py            # Example: Platform B publisher (thin wrapper)
├── .env.example                         # Environment variable template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Prerequisites

- **Python 3.8+**
- **Kiro CLI** installed ([kiro.dev](https://kiro.dev))
- **Confluence instance** with REST API access
- **Personal Access Token (PAT)** for Confluence authentication
- **ADF Git repositories** cloned locally (standard ADF Git integration structure)

---

## Quick Start

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-username/confluence-doc-agent.git
cd confluence-doc-agent
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example publishers/.env
```

Edit `publishers/.env`:
```
CONFLUENCE_PAT=your-personal-access-token
CONFLUENCE_BASE_URL=https://your-instance.atlassian.net/wiki/rest/api/content
SPACE=YOUR_SPACE_KEY
```

### 3. Create your first publisher

Copy `publishers/publish_platform_a.py` and customize:

```python
config = {
    "adf_repo": r"/path/to/your/adf-repo/adf_code",
    "confluence_base_url": os.getenv("CONFLUENCE_BASE_URL"),
    "confluence_pat": os.getenv("CONFLUENCE_PAT"),
    "space": os.getenv("SPACE"),
    "parent_page_id": "12345678",          # Your Confluence parent page ID
    "git_repo": "my-adf-repo",
    "git_branch": "main",
    "factory_name": "adf-my-factory-prod",
    "page_title": "adf-my-factory-prod",
    "factory_description": "My factory - ingests ERP data to Snowflake.",
    "prod_overrides": {},
}
```

### 4. Run manually (to test)

```bash
cd publishers
python publish_platform_a.py
```

### 5. Run via Kiro CLI agent

```bash
kiro-cli chat
# Select the confluence-doc-agent
# It will ask: "Which platform would you like to process?"
# Answer and confirm the branch — it handles the rest
```

---

## How the Agent Works

The Kiro CLI agent provides a conversational interface:

```
Agent: Ready to update the Confluence Knowledge Base. 
       Which platform would you like to process?

You:   Platform A

Agent: Platform A uses repository my-adf-repo on branch 'main'.
       Would you like to use this branch or override?

You:   main is fine

Agent: ✓ Published successfully!
       • All pipelines documented
       • Datasets cataloged  
       • Triggers mapped
       • Page updated: adf-my-factory-prod
```

The agent:
1. Asks which platform to process
2. Asks which Git branch to use
3. Runs `git pull` to get latest code
4. Executes the publisher script
5. Reports results

---

## What Gets Documented

For each pipeline, the agent generates:

### Visual Lineage Diagram
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Source     │────▶│  ADF        │────▶│Intermediate │────▶│  Target     │
│  System     │     │  Pipeline   │     │  Storage    │     │  System     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

### Pipeline Details Panel
- Description, Schedule, Timezone, Retry Policy, Folder, Trigger State

### Lineage Summary Panel
- Source System, Intermediate, Target System, Load Method, Stored Procedure

### Dependencies Panel
- Parent Pipeline, Child Pipelines, Upstream triggers (active/stopped count)

### Additional Inventories
- Trigger Inventory (all triggers with state, frequency, timezone)
- Linked Service Inventory (connections, auth types, integration runtimes)

---

## Adding New Platforms

Each platform is a thin wrapper (~20 lines):

```python
"""My New Platform Publisher"""
import os
from dotenv import load_dotenv
from adf_kb_common import AdfKbPublisher

load_dotenv()

config = {
    "adf_repo": r"/path/to/new-platform-repo/adf_code",
    "confluence_base_url": os.getenv("CONFLUENCE_BASE_URL"),
    "confluence_pat": os.getenv("CONFLUENCE_PAT"),
    "space": os.getenv("SPACE"),
    "parent_page_id": "YOUR_PAGE_ID",
    "git_repo": "new-platform-repo",
    "git_branch": "main",
    "factory_name": "adf-new-platform-prod",
    "page_title": "adf-new-platform-prod",
    "factory_description": "Description of what this factory does.",
    "prod_overrides": {},
}

if __name__ == "__main__":
    publisher = AdfKbPublisher(config)
    publisher.publish()
```

---

## ADF Repository Structure

The agent expects the standard ADF Git integration folder structure:

```
your-adf-repo/
└── adf_code/
    ├── pipeline/
    │   ├── p_my_pipeline.json
    │   └── ...
    ├── dataset/
    │   ├── ds_my_dataset.json
    │   └── ...
    ├── linkedService/
    │   ├── ls_my_snowflake.json
    │   └── ...
    ├── trigger/
    │   ├── tr_daily_trigger.json
    │   └── ...
    └── integrationRuntime/
        ├── ir_selfhosted.json
        └── ...
```

---

## Production Overrides

If your ADF repo uses dev/test linked services by default, use `prod_overrides` to map production values:

```python
"prod_overrides": {
    "ls_snowflake_main": {
        "server": "your-prod-account.snowflakecomputing.com",
        "database": "PROD_DWH"
    },
    "ls_sqlserver_onprem": {
        "server": "prod-sql-server.your-domain.com",
        "database": "ProductionDB"
    },
}
```

---

## Security

- **No secrets in code** — All credentials are in `.env` (gitignored)
- **PAT isolation** — The AI agent never sees the token; Python loads it from environment
- **Restricted shell** — The agent can only run `python.*publish_.*`, `git pull.*`, `git checkout.*`
- **Read-only by default** — The agent uses `read` and `grep` for code analysis

---

## Extending to Other Technologies

The pattern is extensible. To support Azure Functions, Kubernetes, or other technologies:

1. Create a new engine class (e.g., `functions_kb_common.py`) that:
   - Parses the relevant file format (function.json, YAML manifests, etc.)
   - Extracts operational metadata (triggers, bindings, dependencies)
   - Generates Confluence HTML
   - Publishes via the same REST API pattern

2. Create thin publisher wrappers for each deployment

3. Add scan rules to the steering document

The core concepts are identical — only the parser changes.

---

## Confluence API Notes

- Uses **Storage format** (Confluence's internal HTML dialect)
- Supports Confluence macros (`ac:structured-macro` for TOC, anchors)
- Creates page if it doesn't exist; updates (with version increment) if it does
- Requires `Content-Type: application/json` and `Authorization: Bearer <PAT>`

### Finding Your Parent Page ID

Navigate to the parent page in Confluence → click `...` → `Page Information` → the ID is in the URL.

### Confluence Server vs. Cloud

- **Server/Data Center**: `https://your-instance.com/rest/api/content`
- **Cloud**: `https://your-instance.atlassian.net/wiki/rest/api/content`

---

## License

MIT — use it, modify it, share it.

---

## Credits

Built with [Kiro CLI](https://kiro.dev) by a data architect who was tired of writing documentation manually.
