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
OUTPUT_FILENAME = "jira_prompt.txt"
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
# FUNCTION TO GENERATE PROMPT WITH GEMINI
# =======================================================================
def generate_enhanced_prompt_with_gemini(jira_context: str):
    """
    Uses Gemini to construct the full, enhanced prompt based on Jira context.
    """
    print("\n--- Generating Full Prompt with Gemini ---")
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
    You are an expert Jira prompt engineer. Your goal is to construct a complete and highly effective prompt.
    You have been provided with a detailed, machine-generated breakdown of a Jira instance below under "DETAILED JIRA INSTANCE CONTEXT".

    Your task is to generate a final prompt that includes the following, in this exact order:
    1.  An "OVERVIEW" section that you will write.
    2.  The full "DETAILED JIRA INSTANCE CONTEXT" provided to you.
    3.  A section of "IMPORTANT JQL NOTES" that you will write.
    4.  A section with 7 new, complex, and insightful examples of questions and their corresponding JQL queries.

    CRITICAL INSTRUCTIONS:
    - Your entire response will be the final content for the prompt. Start your response *directly* with `## OVERVIEW:`. Do not include any preamble or other text.
    - **OVERVIEW:** Write a concise, natural language summary describing what this Jira instance appears to be used for, based on the project names, issue types, and fields.
    - **IMPORTANT JQL NOTES:** Create a bulleted list of key JQL syntax rules and best practices. Include notes on `currentUser()`, `EMPTY`, the difference between `=` (exact match) and `~` (text contains), using `in` for multiple values, and date functions like `startOfMonth()`.
    - **EXAMPLES:** The examples must follow the exact format: `**Question:** "..."` followed on a new line by `**JQL Query:** "..."`. The JQL query must be a single line. These examples must be more complex than simple single-clause queries. Use functions, multiple `AND/OR` clauses, and `ORDER BY`.

    ---
    {jira_context}
    """

    print("Sending request to Gemini... (This may take a moment)")
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
    Connects to Jira, analyzes its metadata, uses Gemini to build a final prompt,
    and writes it to a text file.
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

    # 3. Use Gemini to generate the enhanced parts of the prompt
    enhanced_prompt_part = generate_enhanced_prompt_with_gemini(dynamic_jira_context)

    if not enhanced_prompt_part:
        print("\n❌ Prompt generation failed. No file will be written.")
        return

    # 4. Write the final prompt to the output file
    try:
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            f.write(enhanced_prompt_part)
        print(f"\n✅ Success! The complete, Gemini-enhanced prompt has been saved to: **{OUTPUT_FILENAME}**")
        print("You can now copy the content of this file and paste it into your main agent prompt.")
    except IOError as e:
        print(f"\n❌ Error saving file: {e}")

if __name__ == "__main__":
    main()
