from mcp_servers._base import run

if __name__ == "__main__":
    run("customer_io", tool_names=["create_campaign_draft", "trigger_broadcast"])
