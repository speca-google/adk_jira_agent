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

# tools.py
import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# --- Jira API Connection Details (from .env) ---
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL")
JIRA_API_USER = os.environ.get("JIRA_API_USER")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")

# Setup for authenticated requests
jira_auth = HTTPBasicAuth(JIRA_API_USER, JIRA_API_TOKEN) if all([JIRA_BASE_URL, JIRA_API_USER, JIRA_API_TOKEN]) else None
jira_headers = {"Accept": "application/json", "Content-Type": "application/json"}

def query_jira(jql_query: str, max_results: int = 50, start_at: int = 0) -> dict:
    """
    Executes a raw JQL query against the Jira API and returns the results as JSON.
    This function supports pagination through the 'start_at' parameter.

    Args:
        jql_query (str): The complete and valid JQL query string to execute.
        max_results (int): The maximum number of issues to return per page.
        start_at (int): The index of the first issue to return (for pagination).

    Returns:
        dict: A dictionary containing the JSON response from the Jira API on success,
              or an error message on failure.
    """
    if not jira_auth:
        return {"error": "Jira API credentials are not configured in the environment."}

    # The API endpoint for searching issues
    api_url = f"{JIRA_BASE_URL}/rest/api/3/search"

    # The payload for the API request.
    # It now includes startAt for pagination.
    payload = {
        "jql": jql_query,
        "maxResults": max_results,
        "startAt": start_at,
        "fields": ["*all"] # Fetches all available fields for the issues found
    }

    try:
        response = requests.post(api_url, json=payload, headers=jira_headers, auth=jira_auth, timeout=30)
        
        # Raise an exception for bad status codes (4xx or 5xx)
        response.raise_for_status()
        
        # Return the successful JSON response
        return response.json()

    except requests.exceptions.HTTPError as http_err:
        # Try to return a more specific error from Jira's response
        error_details = f"HTTP Error: {http_err}"
        try:
            error_details = response.json()
        except ValueError:
            error_details = response.text
        return {
            "error": "Failed to execute JQL query in Jira.",
            "status_code": response.status_code,
            "jql_sent": jql_query,
            "details": error_details
        }
    except requests.exceptions.RequestException as req_err:
        return {
            "error": f"A connection error occurred: {req_err}",
            "jql_sent": jql_query
        }
