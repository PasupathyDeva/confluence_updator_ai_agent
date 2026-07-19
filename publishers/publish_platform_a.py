"""
Example ADF Publisher - Platform A
Thin wrapper that configures and runs the publishing engine.

CUSTOMIZE: Update the paths, page IDs, and descriptions for your environment.
Run: python publish_platform_a.py
"""
import os
from dotenv import load_dotenv
from adf_kb_common import AdfKbPublisher

load_dotenv()

config = {
    # CUSTOMIZE: Path to your ADF repository's code folder
    # This should point to the folder containing pipeline/, dataset/, linkedService/, trigger/ subfolders
    "adf_repo": r"/path/to/your/repos/your-adf-repo/adf_code",

    # Loaded from .env file
    "confluence_base_url": os.getenv("CONFLUENCE_BASE_URL"),
    "confluence_pat": os.getenv("CONFLUENCE_PAT"),
    "space": os.getenv("SPACE"),

    # CUSTOMIZE: The Confluence parent page ID where documentation will be published
    # Find this in the URL when viewing the parent page: /pages/viewpage.action?pageId=XXXXXXX
    "parent_page_id": "YOUR_PARENT_PAGE_ID",

    # CUSTOMIZE: Repository and factory details
    "git_repo": "your-adf-repo",
    "git_branch": "main",
    "factory_name": "adf-your-factory-prod",
    "page_title": "adf-your-factory-prod",

    # CUSTOMIZE: One-line description shown at the top of the documentation page
    "factory_description": "Main factory - batch ingestion of ERP and manufacturing data to Snowflake via ADLS.",

    # OPTIONAL: Production linked service overrides
    # Use this when dev/test linked services point to different servers than prod
    "prod_overrides": {
        # "ls_your_snowflake": {"server": "your-account.snowflakecomputing.com", "database": "YOUR_DWH"},
        # "ls_your_sqlserver": {"server": "your-prod-server.database.windows.net", "database": "your-prod-db"},
    },
}

if __name__ == "__main__":
    publisher = AdfKbPublisher(config)
    publisher.publish()
