import json
import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

from .utils import optimize_jira_response, json_to_markdown, save_json_for_debug

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
        
        # Get the raw JSON response
        raw_json_data = response.json()
        #save_json_for_debug(raw_json_data,"raw_data.json")


        # Optimize the JSON response
        optimized_json_data = optimize_jira_response(raw_json_data)
        #save_json_for_debug(optimized_json_data,"optmized_data.json")

        # Transform json respons into markdown to optmize the understand of the Agent
        markdown_response = {"results_markdown": json_to_markdown(optimized_json_data)}
        #save_json_for_debug(markdown_response,"markdown_data.json")

        # Return the optimized JSON response for further use
        return  markdown_response

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
