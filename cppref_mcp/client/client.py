import argparse
import asyncio
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def search_cppreference(session: ClientSession,
                              query: str) -> None:
    '''Calls the search_cppreference MCP tool and prints the results.'''
    print(f'Searching for: {query}')
    result = await session.call_tool('search_cppreference',
                                     {'query': query})
    if hasattr(result, 'content') and result.content:
        print('Search Results:')
        print(result.content[0].text)
    else:
        print(f'Error or no results: {result}')


async def get_cppreference_page(session: ClientSession,
                                url: str) -> None:
    '''Calls the get_cppreference_page MCP tool and prints the results.'''
    print(f'Retrieving page: {url}')
    result = await session.call_tool('get_cppreference_page',
                                     {'url': url})
    if hasattr(result, 'content') and result.content:
        print('Page Content (Markdown):')
        # Print first 500 characters to avoid flooding console if it's long
        content = result.content[0].text
        print(content[:10000] + ('...' if len(content) > 10000 else ''))
    else:
        print(f'Error or no results: {result}')


async def main() -> int:
    parser = argparse.ArgumentParser(description='cppreference MCP  test client')
    parser.add_argument('command', help='command to execute, "search" or "get"')
    parser.add_argument('--server', required=False, help='server executable path')
    parser.add_argument('--log-dir', required=False, help='directory for server log files')
    parser.add_argument('--query', required=False, help='query to search for')
    parser.add_argument('--url', required=False, help='URL to retrieve')
    args = parser.parse_args()

    if args.command not in ['search', 'get']:
        print('Invalid command. Use "search" or "get".')
        return 1
    if args.command == 'search' and not args.query:
        print('Please provide a query to search for.')
        return 1
    if args.command == 'get' and not args.url:
        print('Please provide a URL to retrieve.')
        return 1
    if args.server:
        server_script = Path(args.server)
        if not Path.exists(server_script):
            print(f'Server executable not found at: {server_script}')
            return 1
    else:
        print('Server executable path not provided.')
        return 1
    if args.log_dir:
        log_dir = Path(args.log_dir)

    server_args = [str(server_script)]
    if args.log_dir:
        server_args.extend(['--log-dir', str(log_dir)])
    server_params = StdioServerParameters(
        command=sys.executable,
        args=server_args,
        env=None
    )

    print('Connecting to MCP server...')
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            if args.command == 'search':
                await search_cppreference(session, args.query)
            if args.command == 'get':
                await get_cppreference_page(session, args.url)

    return 0

if __name__ == '__main__':
    ret = asyncio.run(main())
    sys.exit(ret)
