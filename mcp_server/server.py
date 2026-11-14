"""MCP server for Resume Tailor.

Exposes the app's services as MCP tools so an agent (Milestone 3)
can fetch job postings, research companies, read resumes, and look
up past applications through one interface. Runs over stdio.
"""
from mcp.server.mcpserver import MCPServer

from mcp_server.tools import (
    fetch_job_posting,
    get_past_applications,
    read_resume,
    research_company,
)


def create_server() -> MCPServer:
    """Build the MCP server with its name and instructions."""
    server = MCPServer(
        name="resume-tailor",
        instructions=(
            "Tools for tailoring a resume to a job posting. "
            "Fetch the posting, research the company, read the "
            "user's resume, and check past applications before "
            "rewriting anything. Every claim in an output must "
            "come from the resume or the posting."
        ),
    )

    server.tool()(fetch_job_posting)
    server.tool()(research_company)
    server.tool()(read_resume)
    server.tool()(get_past_applications)

    return server


server = create_server()


def main() -> None:
    """Run the server over stdio."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
