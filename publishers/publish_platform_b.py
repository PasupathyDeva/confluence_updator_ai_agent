"""
Example ADF Publisher - Platform B (Business Critical)
Shows how to configure a second factory with different settings.

Run: python publish_platform_b.py
"""
import os
from dotenv import load_dotenv
from adf_kb_common import AdfKbPublisher

load_dotenv()

config = {
    "adf_repo": r"/path/to/your/repos/your-adf-repo-bc/adf_code",
    "confluence_base_url": os.getenv("CONFLUENCE_BASE_URL"),
    "confluence_pat": os.getenv("CONFLUENCE_PAT"),
    "space": os.getenv("SPACE"),
    "parent_page_id": "YOUR_PARENT_PAGE_ID",
    "git_repo": "your-adf-repo-bc",
    "git_branch": "main",
    "factory_name": "adf-your-factory-bc-prod",
    "page_title": "adf-your-factory-bc-prod",
    "factory_description": "Business Critical factory - high-priority real-time ingestion pipelines.",
    "prod_overrides": {},
}

if __name__ == "__main__":
    publisher = AdfKbPublisher(config)
    publisher.publish()
