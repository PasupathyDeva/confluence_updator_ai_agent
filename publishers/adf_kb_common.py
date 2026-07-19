"""
Confluence Documentation Publisher - Core Engine
Scans ADF repositories and publishes comprehensive documentation to Confluence.
Each platform publisher imports this and provides only its configuration.

Supports: Azure Data Factory (built-in), extensible to Azure Functions, Kubernetes, etc.
"""
import json, os, glob, re, requests
from datetime import datetime
from html import escape as html_escape
from collections import defaultdict


class AdfKbPublisher:
    """Scans an ADF repository and publishes comprehensive documentation to Confluence."""

    def __init__(self, config):
        """
        config dict must contain:
            adf_repo: str - path to the ADF code folder (containing pipeline/, dataset/, etc.)
            confluence_base_url: str - Confluence REST API base URL
            confluence_pat: str - Personal Access Token
            space: str - Confluence space key
            parent_page_id: str - parent page to publish under
            git_repo: str - repository name (for display)
            git_branch: str - branch name (for display)
            factory_name: str - factory identifier
            page_title: str - Confluence page title
            factory_description: str - one-line description for the page header
            prod_overrides: dict - linked service production overrides (optional)
        """
        self.adf_repo = config["adf_repo"]
        self.confluence_base_url = config["confluence_base_url"]
        self.confluence_pat = config["confluence_pat"]
        self.space = config["space"]
        self.parent_page_id = config["parent_page_id"]
        self.git_repo = config["git_repo"]
        self.git_branch = config["git_branch"]
        self.factory_name = config["factory_name"]
        self.page_title = config.get("page_title", config["factory_name"])
        self.factory_description = config.get("factory_description", "")
        self.prod_overrides = config.get("prod_overrides", {})

        self.headers = {
            "Authorization": f"Bearer {self.confluence_pat}",
            "Content-Type": "application/json",
        }

        self.linked_services = {}
        self.datasets = {}
        self.pipelines = {}
        self.triggers = []
        self.integration_runtimes = {}

    # ================================================================
    # DATA LOADING
    # ================================================================

    def load_all(self):
        """Load all ADF artifacts from the repository."""
        self._load_linked_services()
        print(f"  Found {len(self.linked_services)} linked services")
        self._load_datasets()
        print(f"  Found {len(self.datasets)} datasets")
        self._load_pipelines()
        print(f"  Found {len(self.pipelines)} pipelines")
        self._load_triggers()
        print(f"  Found {len(self.triggers)} trigger-pipeline mappings")
        self._load_integration_runtimes()
        print(f"  Found {len(self.integration_runtimes)} integration runtimes")

    def _load_linked_services(self):
        for f in glob.glob(os.path.join(self.adf_repo, "linkedService", "*.json")):
            with open(f, encoding="utf-8") as fh:
                ls = json.load(fh)
            name = ls.get("name", "")
            props = ls.get("properties", {})
            tp = props.get("typeProperties", {})
            ls_type = props.get("type", "")
            server = tp.get("server", "")
            database = tp.get("database", "")
            url = tp.get("url", "") or tp.get("baseUrl", "")
            auth_type = tp.get("authenticationType", "")
            connect_via = props.get("connectVia", {}).get("referenceName", "AutoResolveIntegrationRuntime")

            # Extract server/db from connectionString if not directly available
            if not server:
                conn = tp.get("connectionString", "")
                if isinstance(conn, str):
                    if "Data Source=" in conn:
                        server = conn.split("Data Source=")[1].split(";")[0]
                    if "Initial Catalog=" in conn:
                        database = conn.split("Initial Catalog=")[1].split(";")[0]
                    if "Host=" in conn and not server:
                        server = conn.split("Host=")[1].split(";")[0]
                    if "Database=" in conn and not database:
                        database = conn.split("Database=")[1].split(";")[0]
            if not server and tp.get("accountIdentifier"):
                server = tp.get("accountIdentifier")
            if not server and url:
                server = url

            # Apply prod overrides
            ov = self.prod_overrides.get(name, {})
            if "server" in ov:
                server = ov["server"]
            if "database" in ov:
                database = ov["database"]
            if "url" in ov:
                server = ov["url"]

            self.linked_services[name] = {
                "name": name, "type": ls_type, "server": server or url,
                "database": database, "auth_type": auth_type,
                "integration_runtime": connect_via, "file": os.path.basename(f),
            }

    def _load_datasets(self):
        for f in glob.glob(os.path.join(self.adf_repo, "dataset", "*.json")):
            with open(f, encoding="utf-8") as fh:
                ds = json.load(fh)
            name = ds.get("name", "")
            props = ds.get("properties", {})
            ls_ref = props.get("linkedServiceName", {}).get("referenceName", "")
            ds_type = props.get("type", "")
            tp = props.get("typeProperties", {})
            schema_name = tp.get("schema", "") if isinstance(tp.get("schema"), str) else ""
            table_name = tp.get("table", "")
            if isinstance(table_name, dict):
                table_name = ""
            folder = props.get("folder", {}).get("name", "")
            params = props.get("parameters", {})
            location = tp.get("location", {})
            file_system = location.get("fileSystem", "")
            if isinstance(file_system, dict):
                file_system = file_system.get("value", "") or "expression"

            self.datasets[name] = {
                "name": name, "type": ds_type, "linked_service": ls_ref,
                "schema": schema_name, "table": table_name, "folder": folder,
                "parameters": params, "file_system": file_system, "file": os.path.basename(f),
            }


    def _load_pipelines(self):
        for f in glob.glob(os.path.join(self.adf_repo, "pipeline", "*.json")):
            with open(f, encoding="utf-8") as fh:
                pl = json.load(fh)
            name = pl.get("name", "")
            props = pl.get("properties", {})
            activities = props.get("activities", [])
            variables = props.get("variables", {})
            parameters = props.get("parameters", {})
            folder = props.get("folder", {}).get("name", "")
            description = props.get("description", "")
            concurrency = props.get("concurrency", None)

            parsed_activities = []
            stored_procedures = []
            copy_sources = []
            copy_sinks = []
            execute_pipelines = []

            def walk_activities(act_list):
                for act in act_list:
                    act_name = act.get("name", "")
                    act_type = act.get("type", "")
                    depends_on = [d.get("activity", "") for d in act.get("dependsOn", [])]
                    policy = act.get("policy", {})
                    retry = policy.get("retry", 0)
                    timeout = policy.get("timeout", "")
                    tp2 = act.get("typeProperties", {})
                    ls_name = act.get("linkedServiceName", {}).get("referenceName", "")

                    parsed_activities.append({
                        "name": act_name, "type": act_type, "depends_on": depends_on,
                        "retry": retry, "timeout": timeout, "linked_service": ls_name,
                    })

                    if act_type == "SqlServerStoredProcedure":
                        sp_name = tp2.get("storedProcedureName", "")
                        stored_procedures.append({
                            "name": sp_name, "linked_service": ls_name,
                            "parameters": list(tp2.get("storedProcedureParameters", {}).keys()),
                            "activity": act_name,
                        })

                    if act_type == "Copy":
                        src = tp2.get("source", {})
                        inputs = act.get("inputs", [])
                        outputs = act.get("outputs", [])
                        src_dataset = inputs[0].get("referenceName", "") if inputs else ""
                        sink_dataset = outputs[0].get("referenceName", "") if outputs else ""
                        src_query = ""
                        for q_field in ("sqlReaderQuery", "query"):
                            q_val = src.get(q_field)
                            if isinstance(q_val, dict):
                                src_query = q_val.get("value", "")
                                break
                            elif isinstance(q_val, str) and q_val:
                                src_query = q_val
                                break
                        copy_sources.append({"dataset": src_dataset, "query": src_query, "activity": act_name})
                        copy_sinks.append({"dataset": sink_dataset, "activity": act_name})

                    if act_type == "ExecutePipeline":
                        child = tp2.get("pipeline", {}).get("referenceName", "")
                        execute_pipelines.append({"child": child, "activity": act_name})

                    # Recurse into nested activities
                    if act_type == "IfCondition":
                        walk_activities(tp2.get("ifTrueActivities", []))
                        walk_activities(tp2.get("ifFalseActivities", []))
                    if act_type == "ForEach":
                        walk_activities(tp2.get("activities", []))
                    if act_type == "Until":
                        walk_activities(tp2.get("activities", []))
                    if act_type == "Switch":
                        for case in tp2.get("cases", []):
                            walk_activities(case.get("activities", []))
                        walk_activities(tp2.get("defaultActivities", []))

            walk_activities(activities)
            self.pipelines[name] = {
                "name": name, "description": description, "folder": folder,
                "activities": parsed_activities, "variables": variables,
                "parameters": parameters, "stored_procedures": stored_procedures,
                "copy_sources": copy_sources, "copy_sinks": copy_sinks,
                "execute_pipelines": execute_pipelines, "concurrency": concurrency,
                "file": os.path.basename(f),
            }

    def _load_triggers(self):
        for f in glob.glob(os.path.join(self.adf_repo, "trigger", "*.json")):
            with open(f, encoding="utf-8") as fh:
                tr = json.load(fh)
            name = tr.get("name", "")
            props = tr.get("properties", {})
            trigger_type = props.get("type", "")
            runtime_state = props.get("runtimeState", "")
            tp = props.get("typeProperties", {})

            if trigger_type == "ScheduleTrigger":
                recurrence = tp.get("recurrence", {})
                freq = recurrence.get("frequency", "")
                interval = recurrence.get("interval", 1)
                tz = recurrence.get("timeZone", "")
                schedule = recurrence.get("schedule", {})
                if freq == "Minute":
                    frequency_str = f"Every {interval} min"
                elif freq == "Hour":
                    frequency_str = f"Every {interval}h"
                elif freq == "Day":
                    hours = schedule.get("hours", [])
                    mins = schedule.get("minutes", [])
                    if hours and mins:
                        frequency_str = f"Daily at {hours[0]:02d}:{mins[0]:02d}"
                    else:
                        frequency_str = f"Every {interval} day(s)"
                else:
                    frequency_str = f"{freq}/{interval}"
                if tz:
                    frequency_str += f" ({tz})"
            elif trigger_type == "BlobEventsTrigger":
                blob_path = tp.get("blobPathBeginsWith", "")
                frequency_str = f"Event: Blob ({blob_path})"
                tz = ""
            else:
                frequency_str = trigger_type
                tz = ""

            for pipeline_entry in props.get("pipelines", []):
                pipeline_ref = pipeline_entry.get("pipelineReference", {}).get("referenceName", "")
                params = pipeline_entry.get("parameters", {})
                self.triggers.append({
                    "name": name, "type": trigger_type, "pipeline": pipeline_ref,
                    "parameters": params, "frequency": frequency_str,
                    "runtime_state": runtime_state, "timezone": tz,
                    "file": os.path.basename(f),
                })

    def _load_integration_runtimes(self):
        for f in glob.glob(os.path.join(self.adf_repo, "integrationRuntime", "*.json")):
            with open(f, encoding="utf-8") as fh:
                ir = json.load(fh)
            name = ir.get("name", "")
            ir_type = ir.get("properties", {}).get("type", "")
            self.integration_runtimes[name] = {"name": name, "type": ir_type}


    # ================================================================
    # LINEAGE EXTRACTION
    # ================================================================

    @staticmethod
    def _parse_tables_from_sql(sql_query):
        """Extract table names from SQL queries."""
        if not sql_query:
            return []
        cleaned = re.sub(r"@\{[^}]*\}", "''", sql_query)
        pattern = r'(?:FROM|JOIN)\s+(\[?\w+\]?\.?\[?\w+\]?(?:\.\[?\w+\]?)?)'
        matches = re.findall(pattern, cleaned, re.IGNORECASE)
        tables = []
        seen = set()
        for m in matches:
            t = m.replace("[", "").replace("]", "").strip()
            if t.lower() in ("select", "openjson", "") or t.startswith("'"):
                continue
            if t not in seen:
                seen.add(t)
                tables.append(t)
        return tables

    def _get_pipeline_lineage(self, p):
        """Extract end-to-end lineage for a pipeline."""
        src_info = {"type": "N/A", "database": "N/A", "schema": "N/A", "table": "N/A",
                    "is_adls": False, "file_system": "N/A", "account": "N/A", "format": "N/A"}
        sink_info = {"type": "N/A", "database": "N/A", "schema": "N/A", "table": "N/A",
                     "is_adls": False, "file_system": "N/A", "account": "N/A", "format": "N/A"}
        intermediate_info = None
        copy_info = {"name": "N/A", "ir": "N/A", "retry": "N/A", "timeout": "N/A"}
        load_method = "Insert"
        sp_name = "N/A"

        # Step 1: Source from first Copy activity
        if p["copy_sources"]:
            first_src = p["copy_sources"][0]
            src_ds = self.datasets.get(first_src.get("dataset", ""), {})
            src_ls = self.linked_services.get(src_ds.get("linked_service", ""), {})
            src_info["type"] = src_ls.get("type", "N/A")
            src_info["database"] = src_ls.get("database", "") or "N/A"
            src_info["schema"] = src_ds.get("schema", "") or "N/A"
            src_info["table"] = src_ds.get("table", "") or "N/A"
            src_info["format"] = src_ds.get("type", "N/A")
            copy_info["name"] = first_src.get("activity", "N/A")
            copy_info["ir"] = src_ls.get("integration_runtime", "N/A")

            if src_ls.get("type", "") in ("AzureBlobFS", "AzureBlobStorage"):
                src_info["is_adls"] = True
                server = src_ls.get("server", "")
                match = re.search(r'https?://([^.]+)', server)
                src_info["account"] = match.group(1) if match else server

            query = first_src.get("query", "")
            if query:
                tables = self._parse_tables_from_sql(query)
                if tables and src_info["table"] == "N/A":
                    src_info["table"] = ", ".join(tables[:3])

            for act in p["activities"]:
                if act["name"] == first_src.get("activity", ""):
                    copy_info["retry"] = str(act.get("retry", "N/A"))
                    copy_info["timeout"] = act.get("timeout", "N/A")
                    break

        # Step 2: Check for Script/SP activities that indicate final target
        final_target_found = False
        for act in p["activities"]:
            if act["type"] in ("Script", "SqlServerStoredProcedure") and act.get("linked_service"):
                ls = self.linked_services.get(act["linked_service"], {})
                ls_type = ls.get("type", "")
                if ls_type in ("SnowflakeV2", "Snowflake", "AzureSqlDatabase", "SqlServer"):
                    if p["copy_sources"] or not p["copy_sources"]:
                        sink_info["type"] = ls_type
                        sink_info["database"] = ls.get("database", "") or "N/A"
                        sink_info["table"] = "N/A"
                        sp_name = act["name"]
                        load_method = "COPY INTO / Stored Procedure"
                        final_target_found = True
                        if not p["copy_sources"]:
                            copy_info["name"] = act["name"]
                            copy_info["ir"] = ls.get("integration_runtime", "N/A")
                            src_info["type"] = ls_type
                            src_info["database"] = ls.get("database", "") or "N/A"
                            load_method = "Stored Procedure / Script"
                        break

        # Step 3: If final target found, Copy sink = intermediate
        if final_target_found and p["copy_sinks"]:
            last_sink = p["copy_sinks"][-1]
            sink_ds = self.datasets.get(last_sink.get("dataset", ""), {})
            sink_ls = self.linked_services.get(sink_ds.get("linked_service", ""), {})
            if sink_ls.get("type", "") in ("AzureBlobFS", "AzureBlobStorage"):
                server = sink_ls.get("server", "")
                match = re.search(r'https?://([^.]+)', server)
                account = match.group(1) if match else "unknown"
                intermediate_info = {
                    "storage": "ADLS Gen2",
                    "account": account,
                    "file_system": sink_ds.get("file_system", "") or "landing",
                    "format": sink_ds.get("type", "Avro/Parquet"),
                }

        # Step 4: If no final target override, use Copy sink
        if not final_target_found and p["copy_sinks"]:
            last_sink = p["copy_sinks"][-1]
            sink_ds = self.datasets.get(last_sink.get("dataset", ""), {})
            sink_ls = self.linked_services.get(sink_ds.get("linked_service", ""), {})
            sink_info["type"] = sink_ls.get("type", "N/A")
            sink_info["database"] = sink_ls.get("database", "") or "N/A"
            sink_info["schema"] = sink_ds.get("schema", "") or "N/A"
            sink_info["table"] = sink_ds.get("table", "") or "N/A"
            if sink_ls.get("type", "") in ("AzureBlobFS", "AzureBlobStorage"):
                sink_info["is_adls"] = True
                server = sink_ls.get("server", "")
                match = re.search(r'https?://([^.]+)', server)
                sink_info["account"] = match.group(1) if match else server

        # Step 5: Fallback for pipelines with NO Copy activities
        if not p["copy_sources"] and not final_target_found:
            for act in p["activities"]:
                if act["type"] == "ExecutePipeline":
                    copy_info["name"] = act["name"]
                    load_method = "Execute Pipeline"
                    for ep in p.get("execute_pipelines", []):
                        sink_info["table"] = ep["child"]
                        sink_info["type"] = "Child Pipeline"
                        break
                    break

        if p["stored_procedures"] and sp_name == "N/A":
            sp_name = p["stored_procedures"][0]["name"]

        return src_info, copy_info, intermediate_info, sink_info, load_method, sp_name

    # ================================================================
    # HTML HELPERS
    # ================================================================

    @staticmethod
    def _esc(val):
        if val is None:
            return ""
        return html_escape(str(val))

    def _render_stage_box(self, title, color, icon, fields):
        """Render a colored stage box for the lineage diagram."""
        bg_colors = {"blue": "#E3F2FD", "green": "#E8F5E9", "orange": "#FFF3E0", "red": "#FFEBEE"}
        border_colors = {"blue": "#1565C0", "green": "#2E7D32", "orange": "#E65100", "red": "#C62828"}
        bg = bg_colors.get(color, "#F5F5F5")
        border = border_colors.get(color, "#616161")
        html = f'<td style="vertical-align:top;border:2px solid {border};border-radius:8px;background:{bg};padding:8px;min-width:140px;max-width:180px;">'
        html += f'<p style="text-align:center;font-weight:bold;color:{border};margin:4px 0;">{icon} {self._esc(title)}</p>'
        html += '<hr style="margin:4px 0;"/>'
        for label, value in fields:
            html += f'<p style="margin:2px 0;font-size:11px;"><strong>{self._esc(label)}</strong> : {self._esc(value)}</p>'
        html += '</td>'
        return html

    @staticmethod
    def _render_arrow():
        return '<td style="vertical-align:middle;text-align:center;padding:0 4px;font-size:20px;color:#757575;">&#9654;</td>'


    # ================================================================
    # HTML GENERATION
    # ================================================================

    def build_html(self):
        """Build the complete Confluence HTML page."""
        parts = [
            self._build_header(),
            self._build_statistics(),
            self._build_pipeline_documentation(),
            self._build_trigger_inventory(),
            self._build_linked_service_inventory(),
        ]
        return "\n".join(parts)

    def _build_header(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"""<ac:structured-macro ac:name="anchor"><ac:parameter ac:name="">top</ac:parameter></ac:structured-macro>
<h1>{self._esc(self.factory_name)} - Operations Knowledge Base</h1>
<p><strong>Auto-generated:</strong> {now} | <strong>Repository:</strong> {self._esc(self.git_repo)} ({self._esc(self.git_branch)}) | <strong>Factory:</strong> {self._esc(self.factory_name)}</p>
<p>{self._esc(self.factory_description)}</p>
<ac:structured-macro ac:name="toc"><ac:parameter ac:name="maxLevel">2</ac:parameter></ac:structured-macro><hr/>"""

    def _build_statistics(self):
        html = "<h2>Documentation Statistics</h2><table><tbody>"
        html += f"<tr><th>Pipelines</th><td>{len(self.pipelines)}</td></tr>"
        html += f"<tr><th>Datasets</th><td>{len(self.datasets)}</td></tr>"
        html += f"<tr><th>Triggers</th><td>{len(self.triggers)}</td></tr>"
        html += f"<tr><th>Linked Services</th><td>{len(self.linked_services)}</td></tr>"
        html += f"<tr><th>Integration Runtimes</th><td>{len(self.integration_runtimes)}</td></tr>"
        active = sum(1 for t in self.triggers if t["runtime_state"] == "Started")
        html += f"<tr><th>Active Triggers</th><td>{active} / {len(self.triggers)}</td></tr>"
        html += "</tbody></table>"
        html += '<p style="text-align:right;margin:8px 0;"><a href="#top"><strong>&#11014; Back to Top</strong></a></p>'
        return html

    def _build_pipeline_documentation(self):
        now = datetime.now().strftime("%d-%b-%Y %H:%M")
        e = self._esc
        html = "<h2>1. Pipeline Documentation</h2>"
        html += "<p><em>Each pipeline is documented with an end-to-end data lineage diagram.</em></p>"

        trigger_map = defaultdict(list)
        for t in self.triggers:
            trigger_map[t["pipeline"]].append(t)

        for pname in sorted(self.pipelines.keys()):
            p = self.pipelines[pname]
            trigs = trigger_map.get(pname, [])
            trig_freq = trigs[0]["frequency"] if trigs else "N/A"
            trig_tz = trigs[0].get("timezone", "") if trigs else ""
            trig_state = trigs[0]["runtime_state"] if trigs else "N/A"

            src_info, copy_info, intermediate_info, sink_info, load_method, sp_name = self._get_pipeline_lineage(p)

            # Pipeline card
            html += f'<div style="border:1px solid #BDBDBD;border-radius:8px;padding:16px;margin:24px 0 12px 0;background:#FAFAFA;">'
            html += f'<p style="font-size:14px;margin:4px 0;"><strong>Pipeline:</strong> {e(pname)} | <strong>Trigger:</strong> {e(trig_freq)} | <strong>Last Updated:</strong> {now}</p>'

            # Flow diagram
            html += '<table style="border-collapse:separate;border-spacing:6px;margin:12px 0;"><tbody><tr>'

            # Source box
            src_type_label = src_info["type"].replace("SqlServer", "SQL Server").replace("AzureSqlDatabase", "Azure SQL")
            if src_info["is_adls"]:
                src_fields = [("Storage", "ADLS Gen2"), ("Account", src_info["account"]), ("Container", src_info["file_system"]), ("Format", src_info["format"])]
            else:
                src_fields = [("Technology", src_type_label), ("Database", src_info["database"]), ("Schema", src_info["schema"]), ("Table(s)", src_info["table"])]
            html += self._render_stage_box("1. Source System", "blue", "&#128451;", src_fields)
            html += self._render_arrow()

            # Pipeline box
            html += self._render_stage_box("2. ADF Pipeline", "green", "&#9881;", [
                ("Activity", copy_info["name"]), ("Int. Runtime", copy_info["ir"]),
                ("Retry", copy_info["retry"]), ("Timeout", copy_info["timeout"])])
            html += self._render_arrow()

            # Intermediate box (if exists)
            if intermediate_info:
                html += self._render_stage_box("3. Intermediate", "orange", "&#128193;", [
                    ("Storage", intermediate_info["storage"]), ("Account", intermediate_info["account"]),
                    ("Container", intermediate_info["file_system"]), ("Format", intermediate_info["format"])])
                html += self._render_arrow()

            # Target box
            sink_type_label = sink_info["type"].replace("AzureSqlDatabase", "Azure SQL").replace("SqlServer", "SQL Server")
            if sink_info.get("is_adls"):
                sink_fields = [("Storage", "ADLS Gen2"), ("Account", sink_info["account"]), ("Container", sink_info["file_system"]), ("Format", sink_info["format"])]
            else:
                sink_fields = [("Technology", sink_type_label), ("Database", sink_info["database"]), ("Schema", sink_info["schema"]), ("Table", sink_info["table"])]
            html += self._render_stage_box("Target", "red", "&#127968;", sink_fields)
            html += '</tr></tbody></table>'

            # Info panels
            html += '<table style="border-collapse:separate;border-spacing:8px;width:100%;"><tbody><tr>'
            # Details panel
            html += '<td style="vertical-align:top;border:1px solid #1565C0;border-radius:8px;padding:10px;width:33%;background:#FAFAFA;">'
            html += '<p style="font-weight:bold;color:#1565C0;">&#128220; Pipeline Details</p>'
            html += f'<ul style="list-style:none;padding-left:0;font-size:12px;">'
            html += f'<li><strong>Description</strong> : {e(p["description"] or "N/A")}</li>'
            html += f'<li><strong>Schedule</strong> : {e(trig_freq)}</li>'
            html += f'<li><strong>Time Zone</strong> : {e(trig_tz or "N/A")}</li>'
            html += f'<li><strong>Retry Policy</strong> : {e(copy_info["retry"])}</li>'
            html += f'<li><strong>Pipeline Folder</strong> : {e(p["folder"] or "N/A")}</li>'
            html += f'<li><strong>Trigger State</strong> : {e(trig_state)}</li></ul></td>'
            # Lineage panel
            html += '<td style="vertical-align:top;border:1px solid #E65100;border-radius:8px;padding:10px;width:33%;background:#FAFAFA;">'
            html += '<p style="font-weight:bold;color:#E65100;">&#128279; Lineage Summary</p>'
            src_full = f"{src_info['database']}.{src_info['schema']}.{src_info['table']}" if src_info["database"] != "N/A" else src_info["table"]
            sink_full = f"{sink_info['database']}.{sink_info['schema']}.{sink_info['table']}" if sink_info["database"] != "N/A" else sink_info["table"]
            intermediate_str = intermediate_info["file_system"] if intermediate_info else "N/A"
            html += f'<ul style="list-style:none;padding-left:0;font-size:12px;">'
            html += f'<li><strong>Source System</strong> : {e(src_full)}</li>'
            html += f'<li><strong>Intermediate</strong> : {e(intermediate_str)}</li>'
            html += f'<li><strong>Target System</strong> : {e(sink_full)}</li>'
            html += f'<li><strong>Load Method</strong> : {e(load_method)}</li>'
            html += f'<li><strong>Stored Procedure</strong> : {e(sp_name)}</li></ul></td>'
            # Dependencies panel
            html += '<td style="vertical-align:top;border:1px solid #6A1B9A;border-radius:8px;padding:10px;width:33%;background:#FAFAFA;">'
            html += '<p style="font-weight:bold;color:#6A1B9A;">&#128268; Dependencies</p>'
            parent_pls = "N/A"
            child_pls = ", ".join(ep["child"] for ep in p.get("execute_pipelines", [])) or "N/A"
            for other_name, other_p in self.pipelines.items():
                for ep in other_p.get("execute_pipelines", []):
                    if ep["child"] == pname:
                        parent_pls = other_name
                        break
            active_trigs = sum(1 for t in trigs if t["runtime_state"] == "Started")
            stopped_trigs = len(trigs) - active_trigs
            upstream = f"{len(trigs)} trigger(s) ({active_trigs} active, {stopped_trigs} stopped)" if trigs else "No triggers (manually or parent-triggered)"
            html += f'<ul style="list-style:none;padding-left:0;font-size:12px;">'
            html += f'<li><strong>Parent Pipeline</strong> : {e(parent_pls)}</li>'
            html += f'<li><strong>Child Pipelines</strong> : {e(child_pls)}</li>'
            html += f'<li><strong>Upstream</strong> : {e(upstream)}</li></ul></td>'
            html += '</tr></tbody></table></div>'
            html += '<p style="text-align:right;margin:8px 0;"><a href="#top"><strong>&#11014; Back to Top</strong></a></p>'

        return html

    def _build_trigger_inventory(self):
        e = self._esc
        html = "<h2>2. Trigger Inventory</h2><table><tbody>"
        html += "<tr><th>Trigger</th><th>Type</th><th>Pipeline</th><th>Frequency</th><th>State</th></tr>"
        for t in sorted(self.triggers, key=lambda x: x["name"]):
            state = "&#9989; Started" if t["runtime_state"] == "Started" else "&#9940; Stopped"
            html += f"<tr><td>{e(t['name'])}</td><td>{e(t['type'])}</td><td>{e(t['pipeline'])}</td><td>{e(t['frequency'])}</td><td>{state}</td></tr>"
        html += "</tbody></table>"
        html += '<p style="text-align:right;margin:8px 0;"><a href="#top"><strong>&#11014; Back to Top</strong></a></p>'
        return html

    def _build_linked_service_inventory(self):
        e = self._esc
        html = "<h2>3. Linked Service Inventory</h2><table><tbody>"
        html += "<tr><th>Name</th><th>Type</th><th>Server/URL</th><th>Database</th><th>Auth</th><th>Integration Runtime</th></tr>"
        for name in sorted(self.linked_services.keys()):
            ls = self.linked_services[name]
            html += f"<tr><td>{e(name)}</td><td>{e(ls['type'])}</td><td>{e(ls['server'])}</td><td>{e(ls['database'])}</td><td>{e(ls['auth_type'])}</td><td>{e(ls['integration_runtime'])}</td></tr>"
        html += "</tbody></table>"
        html += '<p style="text-align:right;margin:8px 0;"><a href="#top"><strong>&#11014; Back to Top</strong></a></p>'
        return html

    # ================================================================
    # PUBLISH TO CONFLUENCE
    # ================================================================

    def publish(self):
        """Load data, build HTML, publish to Confluence."""
        print(f"Loading artifacts from: {self.adf_repo}")
        self.load_all()
        print("\nBuilding HTML documentation...")
        html = self.build_html()
        print(f"  Generated {len(html):,} characters of HTML")
        print("\nPublishing to Confluence...")
        self._publish_to_confluence(html)
        print("Done!")

    def _publish_to_confluence(self, html):
        """Create or update a Confluence page."""
        title = self.page_title
        search_url = f"{self.confluence_base_url}?title={requests.utils.quote(title)}&spaceKey={self.space}&expand=version"
        resp = requests.get(search_url, headers=self.headers)
        resp.raise_for_status()
        results = resp.json().get("results", [])

        body = {
            "type": "page",
            "title": title,
            "space": {"key": self.space},
            "ancestors": [{"id": self.parent_page_id}],
            "body": {"storage": {"value": html, "representation": "storage"}},
        }

        if results:
            # Update existing page
            page_id = results[0]["id"]
            version = results[0]["version"]["number"] + 1
            body["version"] = {"number": version}
            resp = requests.put(f"{self.confluence_base_url}/{page_id}", json=body, headers=self.headers)
        else:
            # Create new page
            resp = requests.post(self.confluence_base_url, json=body, headers=self.headers)

        if resp.status_code >= 400:
            print(f"Error {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()

        page_url = resp.json().get("_links", {}).get("base", "") + resp.json().get("_links", {}).get("webui", "")
        print(f"Published: {page_url}")
