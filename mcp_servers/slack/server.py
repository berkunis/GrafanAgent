from mcp_servers._base import run

if __name__ == "__main__":
    run("slack", tool_names=["post_message", "request_approval"])
