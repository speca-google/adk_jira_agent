# agent.py
import os
from google.adk.agents import Agent
from dotenv import load_dotenv

# Import the refactored tool and the enhanced prompt
from . import tools
from .prompt import JIRA_PROMPT

# Load environment variables from the .env file
load_dotenv()

# --- Agent Definition ---

# The name of the model to be used by the root agent.
# This should be a powerful model capable of reasoning and function calling.
ROOT_AGENT_MODEL = os.environ.get("ROOT_AGENT_MODEL", "gemini-2.5-flash")

# This is the main agent.
# Its instruction is the comprehensive prompt we've built, which contains all the
# context and reasoning logic. The agent's only tool is the simple query executor.
root_agent = Agent(
    name="jira_agent",
    model=ROOT_AGENT_MODEL,
    description="An agent that understands questions about Jira, generates JQL, executes it, and provides answers.",
    instruction=JIRA_PROMPT,
    tools=[
        tools.query_jira,
    ],
)
