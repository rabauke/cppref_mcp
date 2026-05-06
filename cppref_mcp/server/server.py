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
from fastmcp.tools import tool
import httpx
from markitdown import MarkItDown
from cache import LRUCache


class CppReferenceMCP:
  BASE_URL = 'https://cppreference.com'
  HTTP_TIMEOUT = 10.0
  MAX_SEARCH_RESULTS = 5
  PAGE_SIZE = 1024 * 16


  def __init__(self):
    self.mcp = FastMCP(
        'cppreference',
        instructions='Provides tools for searching and retrieving documentation for the '
                     'C++ programming language from cppreference.com.',
        version='0.1.0'
    )
    self.markitdown = MarkItDown()
    self.search_cache = LRUCache(200)
    self.page_cache = LRUCache(50)

    # Register tools
    self.mcp.add_tool(self.search_cppreference)
    self.mcp.add_tool(self.get_cppreference_page)


  @tool(
      name='search_cppreference',
      annotations={
        'title': 'Search cppreference.com',
        'readOnlyHint': True,
        'idempotentHint': True,
      }
  )
  async def search_cppreference(
      self,
      query: Annotated[
          str,
          'Concise C or C++ documentation search query, such as a symbol, header, keyword, standard feature, or library facility.'
      ],
  ) -> str:
    """
    Search cppreference.com for C or C++ standard library, language, and
    compiler-related documentation.

    Use this tool when a developer or AI assistant needs authoritative
    documentation for a C++ symbol, header, concept, keyword, feature-test
    macro, language rule, library function, class template, algorithm, type
    trait, container, iterator, utility, or standard feature.

    Good queries are usually concise and cppreference-oriented, for example:
    "std::vector", "std::ranges::sort", "constexpr", "std::optional",
    "std::move", "template argument deduction", "operator<=>",
    "std::filesystem::path", or "C++20 concepts".

    Returns a JSON string with:
    - "query": the normalized search query.
    - "result_urls": up to five matching cppreference.com URLs.

    After selecting the most relevant URL, call get_cppreference_page to
    retrieve the page content as Markdown.
    """
    query = query.strip()

    cached = self.search_cache.get(query)
    if cached:
      logging.info('Using cached results for query: %s', query)
      return cached

    logging.info('Searching cppreference for: %s', query)
    search_url = urljoin(self.BASE_URL, 'index.php')
    params = {
      'title': 'Special:Search',
      'search': query,
    }

    try:
      async with httpx.AsyncClient(
          timeout=self.HTTP_TIMEOUT,
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
          result = json.dumps({'query': query, 'result_urls': urls})
          self.search_cache.put(query, result)
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

        if len(urls) >= self.MAX_SEARCH_RESULTS:
          break

      logging.info('Found %d results for query: %s', len(urls), query)
      result = json.dumps({'query': query, 'result_urls': urls})
      self.search_cache.put(query, result)
      return result

    except Exception as exc:
      logging.exception('Error during search: %s', exc)
      return f'Error: Search failed: {str(exc)}'


  @tool(
      name='get_cppreference_page',
      annotations={
        'title': 'Get page from cppreference.com',
        'readOnlyHint': True,
        'idempotentHint': True,
      }
  )
  async def get_cppreference_page(
      self,
      url: Annotated[
          str,
          'HTTPS URL of a cppreference.com documentation page to retrieve.'
      ],
      cursor: Annotated[
          str | None,
          'Pagination cursor returned by a previous get_cppreference_page call, or null/omitted for the first page.'
      ] = None,
  ) -> str:
    """
    Retrieve a cppreference.com documentation page and return its content as
    Markdown suitable for use by an AI coding assistant.

    Use this tool after search_cppreference has returned a relevant URL, or
    when the exact cppreference.com HTTPS URL is already known. This is
    useful for answering C++ questions with authoritative details about
    syntax, overloads, template parameters, constraints, feature availability,
    examples, notes, defect reports, and standard-version differences.

    Only HTTPS URLs whose domain is cppreference.com are accepted.

    The response is a JSON string with:
    - "content": a Markdown fragment of the requested page.
    - "next_cursor": a string cursor for the next fragment, or null if the
      full page has been returned.

    Large pages are paginated. If "next_cursor" is not null, call this tool
    again with the same URL and cursor=next_cursor to retrieve the next
    Markdown fragment. Continue until "next_cursor" is null.
    """
    url = url.strip()

    parsed_base_url = urlparse(self.BASE_URL)
    parsed_url = urlparse(url)

    if parsed_url.netloc != parsed_base_url.netloc or parsed_url.scheme != 'https':
      logging.error('Invalid URL or domain: %s', url)
      return f'Error: Only HTTPS pages from {parsed_base_url.netloc} are allowed.'

    # Handle cursor
    start_index = 0
    if cursor:
      try:
        start_index = int(cursor)
      except ValueError:
        logging.error('Invalid cursor: %s', cursor)
        return 'Error: Invalid cursor format. Expected an integer.'

    cached = self.page_cache.get(url)
    if cached:
      logging.info('Using cached results for page: %s', url)
      full_content = cached
    else:
      logging.info('Retrieving page: %s', url)

      try:
        async with httpx.AsyncClient(
            timeout=self.HTTP_TIMEOUT,
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
            a_tag['href'] = urljoin(self.BASE_URL, href)

        html_stream = BytesIO(str(soup).encode('utf-8'))
        converted = self.markitdown.convert_stream(
            html_stream,
            file_extension='.html',
        )
        full_content = converted.text_content
        self.page_cache.put(url, full_content)

      except Exception as exc:
        logging.exception('Error retrieving or converting page: %s', exc)
        return f'Error: Failed to process page: {str(exc)}'

    # Implement pagination
    end_index = min(start_index + self.PAGE_SIZE, len(full_content))
    page_content = full_content[start_index:end_index]

    next_cursor = None
    if end_index < len(full_content):
      next_cursor = str(end_index)

    result = {
      'content': page_content,
      'next_cursor': next_cursor
    }
    return json.dumps(result)


  def run(self):
    self.mcp.run()


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

  server = CppReferenceMCP()
  server.run()
