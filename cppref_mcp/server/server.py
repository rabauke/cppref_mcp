import argparse
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import List
from urllib.parse import urlparse
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from fastmcp import FastMCP
from markitdown import MarkItDown

base_url = 'https://cppreference.com'

# Initialize FastMCP server
mcp = FastMCP('cppreference')

# Initialize MarkItDown
markitdown = MarkItDown()


def setup_logging(log_dir: str) -> None:
  '''Sets up logging with rotation.'''
  if not os.path.exists(log_dir):
    os.makedirs(log_dir)

  log_file = os.path.join(log_dir, 'cppref_mcp.log')
  handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024,
                                backupCount=5)
  formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  handler.setFormatter(formatter)

  logger = logging.getLogger()
  logger.setLevel(logging.INFO)
  logger.addHandler(handler)


@mcp.tool()
async def search_cppreference(query: str) -> str:
  '''
  Searches the cppreference.com website for the specified query.  Returns a list of up to five
  URLs of pages containing the search results.
  '''
  logging.info(f'Searching cppreference for: {query}')
  search_url = urljoin(base_url, 'index.php')
  params = {
    'title': 'Special:Search',
    'search': query,
  }

  async with httpx.AsyncClient() as client:
    response = await client.get(search_url, params=params,
                                follow_redirects=True,
                                timeout=10.0)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    search_results = soup.select('.mw-search-result-heading a')

    if not search_results:
      final_url = str(response.url)
      if 'Special:Search' not in final_url and 'index.php' not in final_url:
        logging.info(f'Directly redirected to: {final_url}')
        return json.dumps([final_url])

    urls = []
    seen = set()
    for result in search_results:
      href = result.get('href')
      if href:
        full_url = urljoin(str(response.url), href)
        if full_url not in seen:
          seen.add(full_url)
          urls.append(full_url)
      if len(urls) >= 5:
        break

    logging.info(f'Found {len(urls)} results for query: {query}')
    return json.dumps(urls)


@mcp.tool()
async def get_cppreference_page(url: str) -> str:
  '''
  Retrieves the specified cppreference.com page and returns it as markdown. Ensures only pages
  from cppreference.com are retrieved.
  '''
  logging.info(f'Retrieving page: {url}')
  parsed_base_url = urlparse(base_url)
  parsed_url = urlparse(url)
  if parsed_url.netloc != parsed_base_url.netloc:
    logging.error(f'Invalid domain: {parsed_url.netloc}')
    return f'Error: Only pages from {parsed_base_url} are allowed.'

  async with httpx.AsyncClient() as client:
    response = await client.get(url, follow_redirects=True,
                                timeout=10.0)
    if response.status_code != 200:
      logging.error(f'Failed to retrieve page: {response.status_code}')
      return f'Error: Failed to retrieve page (Status: {response.status_code})'

    soup = BeautifulSoup(response.text, 'html.parser')
    for a_tag in soup.find_all('a'):
      url = a_tag.get('href')
      if url and (url.startswith('/c/') or url.startswith('/cpp/')):
        a_tag['href'] = urljoin(base_url, url)

    # Save to a temporary file for MarkItDown if needed, or use content MarkItDown.convert can
    # take a file-like object or path. For now, let's use a simple approach if MarkItDown
    # supports it. Actually MarkItDown.convert(url) might work but we want to ensure domain
    # validation Let's use the content we already fetched.

    try:
      # MarkItDown doesn't easily support direct HTML string conversion
      # in all versions without a file
      # We'll write to a temp file and convert it.
      import tempfile
      with tempfile.NamedTemporaryFile(suffix='.html',
                                       delete=False) as temp_file:
        temp_file.write(str(soup).encode('utf-8'))
        temp_path = temp_file.name

      result = markitdown.convert(temp_path)
      os.unlink(temp_path)
      return result.text_content
    except Exception as e:
      logging.exception(f'Error converting HTML to Markdown: {e}')
      return f'Error: Failed to convert page to Markdown: {str(e)}'


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    description='cppreference MCP Server')
  parser.add_argument('--log-dir', required=False,
                      help='Directory for log files')
  args = parser.parse_args()

  if args.log_dir:
    setup_logging(args.log_dir)
    logging.info('Starting cppreference MCP Server')
  else:
    logging.disable(logging.CRITICAL)

  mcp.run()
