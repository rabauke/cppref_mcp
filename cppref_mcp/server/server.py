import argparse
import json
import logging
import os
from io import BytesIO
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup
from fastmcp import FastMCP
from markitdown import MarkItDown
from typing import Annotated


base_url = 'https://cppreference.com'
mcp = FastMCP('cppreference',
              instructions='Provides tools for searching and retrieving documentation for the '
                           'C++ programming language from cppreference.com.',
              version='0.1.0')
markitdown = MarkItDown()

search_cppreference_cache = {}
get_cppreference_page_cache = {}


def setup_logging(log_dir: str) -> None:
  '''
  Sets up logging with rotation.
  '''
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


@mcp.tool(name='search_cppreference',
          annotations={'title': 'Search cppreference.com',
                       'readOnlyHint': True,
                       'idempotentHint': True})
async def search_cppreference(query: Annotated[str, 'query string for search cppreference.com']) -> str:
  '''
  Searches the cppreference.com website for the specified query.  Returns a list of up to five
  URLs of pages containing the search results.
  '''

  query: str = query.strip()

  if query in search_cppreference_cache:
    logging.info('Using cached results for query: %s', query)
    return search_cppreference_cache[query]

  logging.info('Searching cppreference for: %s', query)
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
        logging.info('Directly redirected to: %s', final_url)
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

    logging.info('Found %d results for query: %s', len(urls), query)
    search_cppreference_cache[query] = json.dumps(urls)
    return search_cppreference_cache[query]


@mcp.tool(name='get_cppreference_page',
          annotations={'title': 'Get page from cppreference.com',
                       'readOnlyHint': True,
                       'idempotentHint': True})
async def get_cppreference_page(url: Annotated[str, 'url of a page from cppreference.com']) -> str:
  '''
  Retrieves the specified cppreference.com page and returns it as Markdown. Ensures only pages
  from cppreference.com are retrieved.
  '''

  url: str = url.strip()

  parsed_base_url = urlparse(base_url)
  parsed_url = urlparse(url)
  if parsed_url.netloc != parsed_base_url.netloc:
    logging.error('Invalid domain: %s', parsed_url.netloc)
    return f'Error: Only pages from {parsed_base_url} are allowed.'

  if url in get_cppreference_page_cache:
    logging.info('Using cached results for page: %s', url)
    return get_cppreference_page_cache[url]

  logging.info('Retrieving page: %s', url)
  async with httpx.AsyncClient() as client:
    response = await client.get(url, follow_redirects=True,
                                timeout=10.0)
    if response.status_code != 200:
      logging.error('Failed to retrieve page: %d', response.status_code)
      return f'Error: Failed to retrieve page (Status: {response.status_code})'

    soup = BeautifulSoup(response.text, 'html.parser')
    for a_tag in soup.find_all('a'):
      url = a_tag.get('href')
      if url and (url.startswith('/c/') or url.startswith('/cpp/') or url == '/c' or url == '/cpp'):
        a_tag['href'] = urljoin(base_url, url)

    try:
      html_stream = BytesIO(str(soup).encode('utf-8'))
      result = markitdown.convert_stream(
        html_stream,
        file_extension='.html',
      )
      get_cppreference_page_cache[url] = result.text_content
      return get_cppreference_page_cache[url]
    except Exception as e:
      logging.exception('Error converting HTML to Markdown: %s', e)
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
