import json
import os 

def _extract_text_from_adf(adf_node: dict | None) -> str:
    """
    Recursively traverses a Jira Atlassian Document Format (ADF) node to extract plain text.
    This is a simplified helper to handle fields like 'description' and 'comment'.

    Args:
        adf_node (dict | None): The ADF JSON object or None.

    Returns:
        str: The concatenated plain text from the ADF structure.
    """
    if not adf_node or not isinstance(adf_node, dict):
        return ""

    text_parts = []
    
    # If the node has a 'text' property, it's a text node.
    if "text" in adf_node and isinstance(adf_node["text"], str):
        text_parts.append(adf_node["text"])

    # Recursively search for content within the node.
    if "content" in adf_node and isinstance(adf_node["content"], list):
        for sub_node in adf_node["content"]:
            text_parts.append(_extract_text_from_adf(sub_node))
            
    return " ".join(filter(None, text_parts))


def _unpack_custom_field_value(value):
    """
    Intelligently unpacks the value from a Jira custom field.
    Handles common structures like dictionaries with a 'value' or 'name' key,
    lists of such dictionaries, and simple primitive types.

    Args:
        value: The value of the custom field.

    Returns:
        The simplified value.
    """
    if value is None:
        return None
    
    # Handle list-based custom fields (e.g., multi-selects, checkboxes)
    if isinstance(value, list):
        # Recursively unpack each item in the list
        return [_unpack_custom_field_value(item) for item in value]

    # Handle dictionary-based custom fields (e.g., single-select, radio buttons)
    if isinstance(value, dict):
        # Common patterns for custom field values
        if 'value' in value:
            return value['value']
        if 'name' in value:
            return value['name']
        if 'displayName' in value:
            return value['displayName']
        # Fallback for complex objects like sprint details, return the dict
        return value

    # For simple values (string, number, boolean), return as is
    return value


def optimize_jira_response(raw_jira_json: dict) -> dict:
    """
    Optimizes the raw JSON response from Jira API by extracting key information
    and dynamically processing all custom fields.

    Args:
        raw_jira_json (dict): The complete JSON response from Jira's search endpoint.

    Returns:
        dict: A simplified dictionary containing essential Jira issue information,
              including all found custom fields.
    """
    if not isinstance(raw_jira_json, dict):
        raise TypeError("Input must be a dictionary.")

    optimized_data = {
        "query_details": {
            "totalIssues": raw_jira_json.get("total", 0),
            "startAt": raw_jira_json.get("startAt",0),
            "maxResults": raw_jira_json.get("startAt",50),
        },
        "issues": []
    }

    for issue in raw_jira_json.get("issues", []):
        fields = issue.get("fields", {})
    
        # Safely get user objects.
        creator_obj = fields.get("creator") or {}
        reporter_obj = fields.get("reporter") or {}
        assignee_obj = fields.get("assignee") or {}

        optimized_issue = {
            "id": issue.get("id"),
            "key": issue.get("key"),
            "summary": fields.get("summary"),
            "description": _extract_text_from_adf(fields.get("description")),
            "issueType": fields.get("issuetype", {}).get("name"),
            "projectKey": fields.get("project", {}).get("key"),
            "projectName": fields.get("project", {}).get("name"),
            "status": fields.get("status", {}).get("name"),
            "statusCategory": fields.get("status", {}).get("statusCategory", {}).get("name"),
            "priority": fields.get("priority", {}).get("name"),
            "labels": fields.get("labels", []),
            "creatorDisplayName": creator_obj.get("displayName"),
            "creatorEmailAddress": creator_obj.get("emailAddress"),
            "reporterDisplayName": reporter_obj.get("displayName"),
            "reporterEmailAddress": reporter_obj.get("emailAddress"),
            "assigneeDisplayName": assignee_obj.get("displayName"),
            "assigneeEmailAddress": assignee_obj.get("emailAddress"),
            "created": fields.get("created"),
            "updated": fields.get("updated"),
        }

        # Add optional standard fields only if they exist
        if fields.get("resolution"):
            optimized_issue["resolution"] = fields["resolution"].get("name")
        if fields.get("resolutiondate"):
            optimized_issue["resolutionDate"] = fields["resolutiondate"]
        if fields.get("duedate"):
            optimized_issue["dueDate"] = fields["duedate"]
        
        # Dinamic Custom Fields Handling
        for field_key, field_value in fields.items():
            if field_key.startswith("customfield_") and field_value is not None:
                # Unpack the custom field value and add it to the issue
                optimized_issue[field_key] = _unpack_custom_field_value(field_value)
        
        # Simplify issue links
        if fields.get("issuelinks"):
            simplified_links = []
            for link in fields["issuelinks"]:
                link_type = link.get("type", {}).get("name")
                
                # A link can be inward or outward
                linked_issue_data = link.get("outwardIssue") or link.get("inwardIssue")
                if not linked_issue_data:
                    continue

                linked_issue_key = linked_issue_data.get("key")
                linked_issue_summary = linked_issue_data.get("fields", {}).get("summary")

                if link_type and linked_issue_key:
                    simplified_links.append({
                        "type": link_type,
                        "direction": "outward" if "outwardIssue" in link else "inward",
                        "linkedIssueKey": linked_issue_key,
                        "linkedIssueSummary": linked_issue_summary,
                        "status": linked_issue_data.get("fields", {}).get("status", {}).get("name")
                    })
            if simplified_links:
                optimized_issue["issueLinks"] = simplified_links
        
        # Simplify comments
        if fields.get("comment", {}).get("comments"):
            simplified_comments = []
            for comment in fields["comment"]["comments"]:
                author_obj = comment.get("author") or {}
                comment_body_text = _extract_text_from_adf(comment.get("body"))
                if comment_body_text:
                    simplified_comments.append({
                        "author": author_obj.get("displayName"),
                        "created": comment.get("created"),
                        "body": comment_body_text
                    })
            if simplified_comments:
                optimized_issue["comments"] = simplified_comments

        optimized_data["issues"].append(optimized_issue)

    return optimized_data


def json_to_markdown(data):
    """
    Converts a JSON object into a generic Markdown format.

    The function is designed to be generic for any JSON representing a list of
    records. It flattens each record into a list of key-value pairs,
    optimizing for token efficiency when used with LLMs.

    Args:
        data (dict or str): The data as a Python dictionary or a JSON string.
                              It's expected to contain a list of objects.

    Returns:
        str: A string containing the data formatted in Markdown.
    """
    if isinstance(data, str):
        try:
            py_data = json.loads(data)
        except json.JSONDecodeError:
            return "Error: Input string is not valid JSON."
    else:
        py_data = data

    records = []
    # Heuristic to find the main list of records in the JSON
    if isinstance(py_data, list):
        records = py_data
    elif isinstance(py_data, dict):
        # Find the first value that is a list of dictionaries
        for value in py_data.values():
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                records = value
                break
    
    # If no list is found, treat the entire dictionary as a single record
    if not records and isinstance(py_data, dict):
        records = [py_data]
    
    if not records:
        return "Error: Could not find a list of records in the provided JSON."

    markdown_output = []
    
    for record in records:
        if not isinstance(record, dict):
            continue

        details_list = []
        for key, value in record.items():
            if value is None:
                formatted_value = "N/A"
            # Serialize complex types (lists, dicts) into a compact JSON string
            elif isinstance(value, (list, dict)):
                formatted_value = f"`{json.dumps(value, separators=(',', ':'))}`"
            else:
                formatted_value = str(value)
            
            # Create the **key**: value format
            details_list.append(f"**{key}:** {formatted_value}")

        markdown_output.append("\n".join(details_list))
        # Use a separator for each record
        markdown_output.append("---")

    return "\n\n".join(markdown_output)


def save_json_for_debug(response_data, filepath="debug_response.json"):
    """
    Saves the JSON data to a specified file.

    Args:
        response_data (dict): The JSON data (dictionary) to be saved.
        filepath (str, optional): The path to the file where the JSON data
                                  will be saved. Defaults to "debug_response.json".
    """
    try:
        # Ensure the directory for the filepath exists
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

        # Save the JSON data to the specified file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, indent=4)
        
        print(f"JSON response saved to: {os.path.abspath(filepath)}")
        print("You can inspect this file for debugging purposes.")
        
    except Exception as e:
        print(f"An unexpected error occurred while saving JSON to {filepath}: {e}")
