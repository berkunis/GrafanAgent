from mcp_servers._base import run

if __name__ == "__main__":
    run("bigquery", tool_names=["query", "describe_table"])
