# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# generate_jira_prompt.py
import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel

# --- Configuration ---
# Load environment variables from your .env file
load_dotenv()

# The output filename for the generated prompt context.
OUTPUT_FILENAME = "jira_context.txt"
# Maximum number of projects to get sample issues from (to avoid being too slow)
MAX_PROJECTS_TO_SAMPLE = 50
# Maximum number of sample issues to get per project
MAX_SAMPLES_PER_PROJECT = 3

# --- Jira API Connection Details (from .env) ---
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")
JIRA_API_USER = os.environ.get("JIRA_API_USER")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")

# --- Google Cloud AI / Gemini Configuration (from .env) ---
GCP_PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
GCP_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-2.5-pro")


# Global session for making authenticated requests
if JIRA_BASE_URL and JIRA_API_USER and JIRA_API_TOKEN:
    jira_auth = HTTPBasicAuth(JIRA_API_USER, JIRA_API_TOKEN)
    jira_headers = {"Accept": "application/json", "Content-Type": "application/json"}
else:
    jira_auth = None
    jira_headers = None
    print("WARNING: Jira environment variables not configured. The script will not be able to connect to Jira.")


# =======================================================================
# HELPER FUNCTIONS TO FETCH JIRA METADATA
# =======================================================================

def get_jira_data(endpoint: str) -> dict | None:
    """Helper function to perform a GET request to a Jira API endpoint."""
    if not jira_auth:
        return None
    try:
        response = requests.get(
            f"{JIRA_BASE_URL}/rest/api/3/{endpoint}",
            headers=jira_headers,
            auth=jira_auth,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Error accessing endpoint {endpoint}: {e}")
        return None

def get_all_projects():
    """Fetches a list of all accessible projects."""
    print("Fetching projects...")
    projects = get_jira_data("project")
    if projects:
        return [{"key": p["key"], "name": p["name"]} for p in projects]
    return []

def get_all_issue_types():
    """Fetches a list of all possible issue types."""
    print("Fetching issue types...")
    issue_types = get_jira_data("issuetype")
    if issue_types:
        return sorted(list(set([it["name"] for it in issue_types]))) # Use set to get unique names
    return []

def get_all_fields():
    """Fetches a list of all system and custom fields."""
    print("Fetching fields...")
    fields = get_jira_data("field")
    if fields:
        return [
            f"- `{f['name']}` (ID: `{f['id']}`, Searchable: {f.get('searchable', False)})"
            for f in fields if f.get('searchable')
        ]
    return []

def get_all_statuses():
    """Fetches a list of all possible issue statuses."""
    print("Fetching statuses...")
    statuses = get_jira_data("status")
    if statuses:
        return sorted(list(set([s["name"] for s in statuses])))
    return []

def get_all_priorities():
    """Fetches a list of all possible issue priorities."""
    print("Fetching priorities...")
    priorities = get_jira_data("priority")
    if priorities:
        return sorted(list(set([p["name"] for p in priorities])))
    return []

def get_sample_issues(project_key: str, limit: int = 3):
    """Gets a few sample issues from a specific project."""
    print(f"  Fetching sample issues for project '{project_key}'...")
    jql = f'project = "{project_key}" ORDER BY created DESC'
    search_params = {
        'jql': jql, 'maxResults': limit, 'fields': ['summary', 'status', 'priority', 'issuetype']
    }
    
    if not jira_auth:
        return "Authentication not configured."
        
    try:
        response = requests.post(
            f"{JIRA_BASE_URL}/rest/api/3/search", headers=jira_headers, auth=jira_auth, json=search_params, timeout=30
        )
        response.raise_for_status()
        data = response.json()
        issues = data.get("issues", [])
        
        if not issues: return "No recent issues found."

        table = "| Key | Type | Summary | Status | Priority |\n|---|---|---|---|---|\n"
        for issue in issues:
            fields, key = issue.get('fields', {}), issue.get('key', 'N/A')
            summary = fields.get('summary', 'N/A')
            status = fields.get('status', {}).get('name', 'N/A')
            priority = fields.get('priority', {}).get('name', 'N/A')
            issue_type = fields.get('issuetype', {}).get('name', 'N/A')
            table += f"| {key} | {issue_type} | {summary} | {status} | {priority} |\n"
        return table

    except requests.exceptions.RequestException as e:
        error_details = "No additional details available."
        if e.response is not None:
            try:
                error_json = e.response.json()
                if 'errorMessages' in error_json and error_json['errorMessages']:
                    error_details = " ".join(error_json['errorMessages'])
                else:
                    error_details = str(error_json)
            except ValueError:
                error_details = e.response.text
        return f"Could not fetch issues. Details: {error_details}"


# =======================================================================
# FUNCTION TO GENERATE *ONLY* JQL EXAMPLES WITH GEMINI
# =======================================================================
def generate_jql_examples_with_gemini(jira_context: str):
    """
    Uses Gemini to construct JQL examples based on the provided Jira context.
    """
    print("\n--- Generating JQL Examples with Gemini ---")
    if not GCP_PROJECT_ID or not GCP_LOCATION:
        print("❌ GCP_PROJECT_ID and GCP_LOCATION must be set in your .env file for Gemini.")
        return None

    try:
        vertexai.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
        model = GenerativeModel(LLM_MODEL)
    except Exception as e:
        print(f"❌ Error initializing Vertex AI: {e}")
        return None

    instruction_for_gemini = f"""
    You are an expert Jira Query Language (JQL) assistant.
    Based on the Jira instance context provided below, your task is to generate a section with exactly 7 new, complex, and insightful examples of questions a user might ask and their corresponding JQL queries.

    CRITICAL INSTRUCTIONS:
    - Your entire response must be ONLY the examples section.
    - Start your response *directly* with `## EXAMPLES`. Do not include any preamble, introduction, or other text before it.
    - Each example must follow this exact format:
      `**Question:** "..."`
      `**JQL Query:** "..."`
    - The JQL query must be a single line.
    - The examples must be more complex than simple single-clause queries. Use functions (like `currentUser()`, `startOfMonth()`), multiple `AND`/`OR` clauses, `ORDER BY`, and reference the actual projects and statuses provided.
    - **For ALL custom fields, you MUST use the ID syntax (`cf[ID]`). DO NOT use the field name in quotes.** The context provides the exact `cf[ID]` syntax to use for each searchable field.
    - Ensure the JQL is valid and highly relevant to the provided context.

    ---
    # JIRA INSTANCE CONTEXT
    {jira_context}
    """

    print("Sending request to Gemini for JQL examples... (This may take a moment)")
    try:
        response = model.generate_content(instruction_for_gemini)
        return response.text
    except Exception as e:
        print(f"❌ An error occurred during the Gemini API call: {e}")
        return None

# =======================================================================
# MAIN ORCHESTRATION FUNCTION
# =======================================================================
def main():
    """
    Connects to Jira, analyzes its metadata, uses Gemini to build JQL examples,
    and writes the full combined prompt to a text file.
    """
    if not jira_auth:
        print("Exiting. Please configure the Jira environment variables in your .env file.")
        return

    print("--- Starting Jira Instance Analysis ---")
    
    # 1. Fetch all dynamic metadata from Jira
    projects = get_all_projects()
    issue_types = get_all_issue_types()
    fields = get_all_fields()
    statuses = get_all_statuses()
    priorities = get_all_priorities()

    # 2. Assemble the dynamic context section using Markdown
    context_lines = ["\n# DETAILED JIRA INSTANCE CONTEXT\n"]
    context_lines.append("This data is extracted directly from your Jira instance.\n")
    context_lines.append("## Accessible Projects:")
    context_lines.extend([f"- **{p['name']}** (Key: `{p['key']}`)" for p in projects])
    context_lines.append("\n---\n")
    context_lines.append("## Possible Issue Types:")
    context_lines.append(f"`{', '.join(issue_types)}`")
    context_lines.append("\n---\n")
    context_lines.append("## Possible Statuses:")
    context_lines.append(f"`{', '.join(statuses)}`")
    context_lines.append("\n---\n")
    context_lines.append("## Possible Priorities:")
    context_lines.append(f"`{', '.join(priorities)}`")
    context_lines.append("\n---\n")
    context_lines.append("## Issue Samples by Project:")
    for project in projects[:MAX_PROJECTS_TO_SAMPLE]:
        context_lines.append(f"\n### Project: **{project['name']}** (`{project['key']}`)")
        samples = get_sample_issues(project['key'], MAX_SAMPLES_PER_PROJECT)
        context_lines.append(samples)
    context_lines.append("\n---\n")
    context_lines.append("## Available Fields for Searching:")
    context_lines.extend(fields)
    dynamic_jira_context = "\n".join(context_lines)

    # 3. Use Gemini to generate *only* the JQL examples
    jql_examples_section = generate_jql_examples_with_gemini(dynamic_jira_context)

    if not jql_examples_section:
        print("\n❌ JQL example generation failed. No file will be written.")
        return
        
    # 4. Define the static (fixed) parts of the prompt
    overview_section ="""## OVERVIEW:
This document provides a detailed context of the available Jira instance metadata to help in constructing accurate JQL (Jira Query Language) queries. Use the information below about projects, issue types, fields, and statuses to answer questions.
"""

    jql_notes_section =\
"""---
## IMPORTANT JQL NOTES
* **Operators**:
    * Use `=` for exact matches (e.g., `status = 'To Do'`).
    * Use `~` for "CONTAINS" searches in text fields (e.g., `summary ~ "login"`).
    * Use `!=`, `!~`, `>`, `<`, `>`=, `<=` for comparisons.
* **Keywords**:
    * Use `IN` to match multiple values (e.g., `priority IN (High, Highest)`).
    * Use `IS EMPTY` or `IS NOT EMPTY` to find issues where a field is blank or not (e.g., `assignee IS EMPTY`).
* **Functions**:
    * `currentUser()`: Refers to the person running the query. (e.g., `reporter = currentUser()`).
    * `startOfDay()`, `startOfWeek()`, `startOfMonth()`, `startOfYear()`: Used for date comparisons. (e.g., `created >= startOfMonth()`). You can use offsets like `"-1w"` for "one week ago".
* **Logic**:
    * Combine clauses with `AND` and `OR`. Use parentheses `()` to group logic.
* **Sorting**:
    * Use `ORDER BY` to sort results (e.g., `ORDER BY priority DESC, created ASC`).
* **Custom Fields (Advanced)**:
    * **Required Syntax**: Custom fields **MUST** be referenced by their ID to ensure queries are reliable, as names can change. The required syntax is `cf[ID]`.
    * **Finding the Syntax**: The `Available Fields` section below provides the exact JQL to use for every searchable field. For custom fields, it will be in the `cf[12345]` format.
    * **Example**: To query the "Story point estimate" field, check the `Available Fields` list to find its JQL syntax (e.g., `cf[10016]`) and then use it: `cf[10016] >= 5`.
    * **Syntax Depends on Field Type**:
        * **Text**: Use the `~` operator. Example: `cf[10011] ~ "API"`.
        * **Number**: Use comparison operators (`=`, `>`, `<`). Example: `cf[10016] > 5`.
        * **Date/Time**: Use date functions. Example: `cf[10023] < "2025/01/01"`.
        * **Select Lists** (Single or Multi-select): Use `IN` or `NOT IN`. Example: `"Focus Areas" IN ("Mobile", "Backend")`.
        * **User Pickers**: Use `=` with the user's name or `currentUser()`. Example: `cf[10003] = currentUser()`.
        * **Dont need confirm with user the custom fields ID, only if you have two or more with same description.**
"""

    # 5. Assemble the final prompt and write to file
    final_prompt_content = (
        f"{overview_section}\n"
        f"{jql_notes_section}\n"
        f"{jql_examples_section}\n"
        f"---\n"
        f"{dynamic_jira_context}"
    )

    try:
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            f.write(final_prompt_content)
        print(f"\n✅ Success! The complete, optimized prompt has been saved to: **{OUTPUT_FILENAME}**")
        print("You can now use the content of this file in your main agent.")
    except IOError as e:
        print(f"\n❌ Error saving file: {e}")

if __name__ == "__main__":
    main()
