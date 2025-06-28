# Jira ADK Agent

This project implements an intelligent agent using the Google Agent Development Kit (ADK). The agent is capable of understanding questions in natural language, converting them into Jira Query Language (JQL), executing the query on the Jira API, and returning the results.

The key feature of this agent is its use of a "prompt engineering" script that inspects the Jira instance to create a rich and detailed context, allowing the AI model to generate much more accurate and complex JQLs.

## Project Structure
```
/adk-jira-agent/                   # Root project folder
|
├── .venv/                         # Virtual environment directory
|
├── jira_agent/                    # Python package containing the agent's source code
│   ├── __init__.py                # Makes the directory a Python package
│   ├── .env                       # File to store credentials (not versioned)
│   ├── agent.py                   # Defines the main agent (root agent)
│   ├── config.yaml                # Agent deployment settings
│   ├── generate_jira_context.py   # Script to analyze Jira and generate the context for your instance
│   ├── jira_context.txt           # Pre-generated improved context file
│   ├── prompt.py                  # Stores the prompt template and joins with the context
│   └── tools.py                   # Contains the tool that executes JQL on Jira
|
├── requirements.txt               # File listing Python dependencies
└── README.md                      # This file
```

## Prerequisites

* Python 3.12 or higher

## Installation and Execution Guide

Follow the steps below to set up and run the project.

### 1. Clone the Repository (Optional)

If you are starting on a new machine, clone the repository.
```
git clone <your-repository-url>
cd adk_jira_agent
````

### 2. Create and Activate the Virtual Environment (venv)

It is a good practice to isolate the project's dependencies in a virtual environment.

```
# Create the virtual environment

python -m venv .venv

# Activate the virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
```

### 3. Install Dependencies

Create a `requirements.txt` file in the root of your project with the following content:
```
google-adk
google-cloud-aiplatform[agent_engines,adk]
requests
python-dotenv
pyyaml
cloudpickle
pydantic
````

Now, install these packages using `pip`.

```
pip install -r requirements.txt
````

### 4. Configure Environment Variables

Create a file named `.env` in the project root and fill it with your credentials.

**`.env` Example:**
```env
# .env
# Replace the values below with your actual Jira credentials and settings.
# Env Variables for Vertex AI 
GOOGLE_GENAI_USE_VERTEXAI="True"
GOOGLE_CLOUD_PROJECT="gcp_project_id" # Project ID from GCP (where Agent is going to run)
GOOGLE_CLOUD_LOCATION="us-central1" # Location


# --- Agent Models ---
# The model used by the main agent to understand user intent.
ROOT_AGENT_MODEL="gemini-2.5-flash"
# The model used by the Jira tool to convert questions into JQL.
JQL_TOOL_MODEL="gemini-2.5-flash"

# --- Jira API Settings ---
# The base URL of your Jira Cloud instance (e.g., https://your-domain.atlassian.net)
JIRA_BASE_URL=""

# The email of the user account that will be used to authenticate with the Jira API.
JIRA_API_USER=""

# The API token generated for the user above.
# See how to generate: https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/
JIRA_API_TOKEN=""
```

### 5. Generate the Jira Context

Run the `generate_jira_prompt.py` script from the root directory. 

It will connect to your Jira instance, collect metadata, and use the Gemini API to generate a complete and optimized prompt file.

```
python generate_jira_prompt.py
```

After execution, a new file named `jira_prompt.txt` will be created in the root directory.

This `jira_prompt.txt` file contains a pre-generated improved prompt based on the context of the specific Jira instance.

### 6. Configure the Agent's Prompt

1. Open the generated file `jira_prompt.txt.txt`.
2. Copy the **entire** content of this file.
3. Open the `adk_jira_agent/prompt.py` file.
4. Paste the copied content inside the triple quotes of the `JQL_PROMPT_TEMPLATE` variable, inserting in the existing content (below the "# DETAILED JIRA INSTANCE CONTEXT").

### 7. Run the Agent

Now that everything is configured, you can start the agent using ADK web. 

```
adk web
```

The `adk web` command will open an web ui to test your agent.