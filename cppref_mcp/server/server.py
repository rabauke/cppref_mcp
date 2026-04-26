import argparse
import json
import logging
import os
from io import BytesIO
from logging.handlers import RotatingFileHandler
from typing import Annotated
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from fastmcp import FastMCP
import httpx
from markitdown import MarkItDown
from cache import LRUCache


BASE_URL = 'https://cppreference.com'
HTTP_TIMEOUT = 10.0
MAX_SEARCH_RESULTS = 5

mcp = FastMCP(
  'cppreference',
  instructions='Provides tools for searching and retrieving documentation for the '
               'C++ programming language from cppreference.com.',
  version='0.1.0'
)
markitdown = MarkItDown()

search_cache = LRUCache(200)
page_cache = LRUCache(50)


def setup_logging(log_dir: str) -> None:
  """
  Sets up logging with rotation.
  """
  if not os.path.exists(log_dir):
    os.makedirs(log_dir)

  log_file = os.path.join(log_dir, 'cppref_mcp.log')
  handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,
    backupCount=5
  )
  formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  )
  handler.setFormatter(formatter)

  logger = logging.getLogger()
  logger.setLevel(logging.INFO)
  logger.addHandler(handler)


@mcp.tool(
  name='search_cppreference',
  annotations={
    'title': 'Search cppreference.com',
    'readOnlyHint': True,
    'idempotentHint': True
  }
)
async def search_cppreference(
  query: Annotated[str, 'query string for search cppreference.com']
) -> str:
  """
  Searches the cppreference.com website for the specified query.
  Returns a list of up to five URLs of pages containing the search results.
  """
  query = query.strip()

  cached = search_cache.get(query)
  if cached:
    logging.info('Using cached results for query: %s', query)
    return cached

  logging.info('Searching cppreference for: %s', query)
  search_url = urljoin(BASE_URL, 'index.php')
  params = {
    'title': 'Special:Search',
    'search': query,
  }

  try:
    async with httpx.AsyncClient(
      timeout=HTTP_TIMEOUT,
      follow_redirects=True
    ) as client:
      response = await client.get(search_url, params=params)

    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    search_results = soup.select('.mw-search-result-heading a')

    if not search_results:
      final_url = str(response.url)

      if 'Special:Search' not in final_url and 'index.php' not in final_url:
        logging.info('Directly redirected to: %s', final_url)
        result = json.dumps([final_url])
        search_cache.put(query, result)
        return result

    urls = []
    seen = set()

    for search_result in search_results:
      href = search_result.get('href')
      if href:
        full_url = urljoin(str(response.url), href)
        if full_url not in seen:
          seen.add(full_url)
          urls.append(full_url)

      if len(urls) >= MAX_SEARCH_RESULTS:
        break

    logging.info('Found %d results for query: %s', len(urls), query)
    result = json.dumps(urls)
    search_cache.put(query, result)
    return result

  except Exception as exc:
    logging.exception('Error during search: %s', exc)
    return f'Error: Search failed: {str(exc)}'


@mcp.tool(
  name='get_cppreference_page',
  annotations={
    'title': 'Get page from cppreference.com',
    'readOnlyHint': True,
    'idempotentHint': True
  }
)
async def get_cppreference_page(
  url: Annotated[str, 'url of a page from cppreference.com']
) -> str:
  """
  Retrieves the specified cppreference.com page and returns it as Markdown.
  Ensures only pages from cppreference.com are retrieved.
  """
  url = url.strip()

  parsed_base_url = urlparse(BASE_URL)
  parsed_url = urlparse(url)

  if parsed_url.netloc != parsed_base_url.netloc or parsed_url.scheme != 'https':
    logging.error('Invalid URL or domain: %s', url)
    return f'Error: Only HTTPS pages from {parsed_base_url.netloc} are allowed.'

  cached = page_cache.get(url)
  if cached:
    logging.info('Using cached results for page: %s', url)
    return cached

  logging.info('Retrieving page: %s', url)

  try:
    async with httpx.AsyncClient(
      timeout=HTTP_TIMEOUT,
      follow_redirects=True
    ) as client:
      response = await client.get(url)

    if response.status_code != 200:
      logging.error('Failed to retrieve page: %d', response.status_code)
      return f'Error: Failed to retrieve page (Status: {response.status_code})'

    soup = BeautifulSoup(response.text, 'html.parser')

    for a_tag in soup.find_all('a'):
      href = a_tag.get('href')
      if href and (
        href.startswith('/c/')
        or href.startswith('/cpp/')
        or href == '/c'
        or href == '/cpp'
      ):
        a_tag['href'] = urljoin(BASE_URL, href)

    html_stream = BytesIO(str(soup).encode('utf-8'))
    converted = markitdown.convert_stream(
      html_stream,
      file_extension='.html',
    )

    page_cache.put(url, converted.text_content)
    return converted.text_content

  except Exception as exc:
    logging.exception('Error retrieving or converting page: %s', exc)
    return f'Error: Failed to process page: {str(exc)}'


if __name__ == '__main__':
  parser = argparse.ArgumentParser(
    description='cppreference MCP Server'
  )
  parser.add_argument(
    '--log-dir',
    required=False,
    help='Directory for log files'
  )
  args = parser.parse_args()

  if args.log_dir:
    setup_logging(args.log_dir)
    logging.info('Starting cppreference MCP Server')
  else:
    logging.disable(logging.CRITICAL)

  mcp.run()
