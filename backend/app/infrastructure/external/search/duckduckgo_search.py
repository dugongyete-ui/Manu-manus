from typing import Optional
import logging
import httpx
import re
from urllib.parse import unquote, urlparse, parse_qs
from bs4 import BeautifulSoup
from app.domain.models.tool_result import ToolResult
from app.domain.models.search import SearchResults, SearchResultItem
from app.domain.external.search import SearchEngine

logger = logging.getLogger(__name__)

class DuckDuckGoSearchEngine(SearchEngine):
    """DuckDuckGo web search engine implementation using HTML scraping"""
    
    def __init__(self):
        self.base_url = "https://html.duckduckgo.com/html/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
    def _extract_real_url(self, ddg_url: str) -> str:
        if not ddg_url:
            return ""
        if ddg_url.startswith('//duckduckgo.com/l/'):
            parsed = urlparse(ddg_url)
            params = parse_qs(parsed.query)
            if 'uddg' in params:
                return unquote(params['uddg'][0])
        if ddg_url.startswith('http'):
            return ddg_url
        return ddg_url
        
    async def search(
        self, 
        query: str, 
        date_range: Optional[str] = None
    ) -> ToolResult:
        params = {"q": query}
        
        if date_range and date_range != "all":
            date_mapping = {
                "past_day": "d",
                "past_week": "w",
                "past_month": "m",
                "past_year": "y"
            }
            if date_range in date_mapping:
                params["df"] = date_mapping[date_range]
        
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=30.0, follow_redirects=True) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                search_results = []
                
                result_items = soup.find_all('div', class_='result')
                
                for item in result_items:
                    try:
                        title = ""
                        link = ""
                        snippet = ""
                        
                        title_tag = item.find('a', class_='result__a')
                        if title_tag:
                            title = title_tag.get_text(strip=True)
                            raw_link = title_tag.get('href', '')
                            link = self._extract_real_url(raw_link)
                        
                        snippet_tag = item.find('a', class_='result__snippet')
                        if snippet_tag:
                            snippet = snippet_tag.get_text(strip=True)
                        
                        if not snippet:
                            snippet_div = item.find('div', class_='result__body')
                            if snippet_div:
                                snippet = snippet_div.get_text(strip=True)
                        
                        if title and link and not link.startswith('https://duckduckgo.com'):
                            search_results.append(SearchResultItem(
                                title=title,
                                link=link,
                                snippet=snippet
                            ))
                    except Exception as e:
                        logger.warning(f"Failed to parse DuckDuckGo result: {e}")
                        continue
                
                results = SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=len(search_results),
                    results=search_results
                )
                
                return ToolResult(success=True, data=results)
                
        except Exception as e:
            logger.error(f"DuckDuckGo Search failed: {e}")
            error_results = SearchResults(
                query=query,
                date_range=date_range,
                total_results=0,
                results=[]
            )
            
            return ToolResult(
                success=False,
                message=f"DuckDuckGo Search failed: {e}",
                data=error_results
            )
