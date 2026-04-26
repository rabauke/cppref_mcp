# MCP Server for cppreference.com

This project provides an MCP (Model Context Protocol) server to access documentation for the C++ programming language from [cppreference.com](https://cppreference.com). 

## Features

Currently, the server supports the following tools:

- `search_cppreference`: Search for C++ documentation and get up to 5 relevant URLs.
- `get_cppreference_page`: Fetch a specific page from cppreference.com and convert it to Markdown.

Only the stdio transport protocol is supported, i.e., the server has to run locally.

The server is at a very early stage of development and might not yet be ready for production use.

## Testing

There is an accompanying MCP client in the `client` directory for testing the server.

## Setting up the server in your IDE

See the documentation of your IDE for instructions on how to set up an MCP server. See, for example:

- [Visual Studio Code](https://code.visualstudio.com/docs/copilot/customization/mcp-servers)
- [Visual Studio](https://learn.microsoft.com/en-us/visualstudio/ide/mcp-servers)
- [Clion](https://www.jetbrains.com/help/clion/mcp-server.html)
- [Junie](https://junie.jetbrains.com/docs/junie-plugin-mcp-settings.html)
- [Zed](https://zed.dev/docs/ai/mcp)
- [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)
