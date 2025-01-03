import streamlit as st
import aiohttp
import asyncio
import string
import logging
from bs4 import BeautifulSoup
from google.api_core import retry
import google.generativeai as genai

# Set up logging for debugging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Oxylabs proxy credentials
PROXY_USER = "customer-kasperpollas12345_Lyt6m-cc-us"
PROXY_PASS = "Snaksnak12345+"
PROXY_HOST = "pr.oxylabs.io"
PROXY_PORT = "7777"
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# Google Gemini API key
GEMINI_API_KEY = "AIzaSyAlxm5iSAsNVLbLvIVAAlxFkIBjkjE0E1Y"
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Gemini model
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# Custom headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.google.com/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Function to fetch Google autosuggest keywords asynchronously
async def get_autosuggest(query, session):
    url = "https://www.google.com/complete/search"
    params = {"q": query, "client": "chrome"}
    logger.debug(f"Fetching autosuggest for: {query}")
    try:
        async with session.get(url, params=params, headers=HEADERS, proxy=PROXY_URL, timeout=10) as response:
            response.raise_for_status()
            data = await response.text()
            logger.debug(f"Raw response for '{query}': {data}")
            # Parse the response, adjust parsing if necessary
            # Assuming it's JSON, but may need adjustment
            json_data = await response.json()
            logger.debug(f"Parsed JSON response for '{query}': {json_data}")
            if isinstance(json_data, list) and len(json_data) > 1:
                return json_data[1]
            else:
                logger.error(f"Unexpected response format for '{query}': {json_data}")
                return []
    except Exception as e:
        logger.error(f"Error fetching autosuggest for '{query}': {e}")
        return []

# Function to generate expanded keyword variations
def generate_expanded_keywords(seed_keyword):
    expanded_keywords = []
    for letter in string.ascii_lowercase:
        expanded_keywords.append(f"{seed_keyword} {letter}")
        expanded_keywords.append(f"{letter} {seed_keyword}")
    logger.debug(f"Generated {len(expanded_keywords)} expanded keywords for: {seed_keyword}")
    return expanded_keywords

# Function to fetch keywords concurrently using asyncio
async def fetch_keywords_concurrently(queries):
    semaphore = asyncio.Semaphore(20)
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = []
        for query in queries:
            async with semaphore:
                task = asyncio.create_task(get_autosuggest(query, session))
                tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f"Fetched {len(results)} keyword results (including errors)")
        return results

# Function to fetch and parse Google SERP asynchronously
async def fetch_google_serp(query, session, limit=5):
    url = f"https://www.google.com/search?q={query}"
    logger.debug(f"Fetching SERP for: {query}")
    try:
        async with session.get(url, headers=HEADERS, proxy=PROXY_URL, timeout=10) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                results = []
                # Update selectors based on current SERP structure
                for result in soup.find_all('div', class_='tF2Cxc')[:limit]:
                    title_element = result.find('h3')
                    title = title_element.get_text().strip() if title_element else "No Title Found"
                    description_element = result.find('span', class_='aCOpRe')
                    description = description_element.get_text().strip() if description_element else "No Description Found"
                    results.append({
                        "title": title,
                        "description": description
                    })
                logger.debug(f"Successfully fetched SERP for: {query}")
                return results
            else:
                logger.error(f"Error fetching SERP for '{query}': Status code {response.status}")
                return f"Error: Status code {response.status}"
    except Exception as e:
        logger.error(f"Error fetching SERP for '{query}': {e}")
        return f"Error: {e}"

# Function to fetch SERP results concurrently using asyncio
async def fetch_serp_results_concurrently(keywords):
    semaphore = asyncio.Semaphore(20)
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = []
        for keyword in keywords:
            async with semaphore:
                task = asyncio.create_task(fetch_google_serp(keyword, session))
                tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f"Fetched {len(results)} SERP results (including errors)")
        return dict(zip(keywords, results))

# Function to analyze keywords with Gemini
def analyze_keywords_with_gemini(keywords, serp_results):
    prompt = """
    [Your prompt here]
    """
    chat_input = "Here is the list of keywords and their SERP results:\n"
    for keyword, results in serp_results.items():
        if isinstance(results, list):
            chat_input += f"Keyword: {keyword}\n"
            for i, result in enumerate(results, start=1):
                if isinstance(result, dict) and "title" in result and "description" in result:
                    chat_input += f"  Result {i}:\n"
                    chat_input += f"    Title: {result['title']}\n"
                    chat_input += f"    Description: {result['description']}\n"
            chat_input += "\n"

    generation_config = {
        "temperature": 1,
        "max_output_tokens": 10000,
    }

    @retry.Retry()
    def call_gemini():
        return gemini_model.generate_content(
            contents=[prompt, prompt + "\n" + chat_input],
            generation_config=generation_config,
        )

    try:
        response = call_gemini()
        return response.text
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        return None

# Streamlit UI
st.title("Google Autosuggest Keyword Fetcher with SERP Results and Gemini Analysis")

# Initialize session state
if "all_keywords" not in st.session_state:
    st.session_state.all_keywords = set()
if "serp_results" not in st.session_state:
    st.session_state.serp_results = {}
if "gemini_output" not in st.session_state:
    st.session_state.gemini_output = None

query = st.text_input("Enter a seed keyword:")

if query:
    # Generate expanded keyword variations
    expanded_keywords = generate_expanded_keywords(query)

    # Fetch autosuggest keywords concurrently
    if st.button("Fetch Keywords"):
        with st.spinner("Fetching autosuggest keywords concurrently..."):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            results = loop.run_until_complete(fetch_keywords_concurrently([query] + expanded_keywords))

            valid_keywords = []
            for result in results:
                if isinstance(result, list):
                    valid_keywords.extend(result)
                elif isinstance(result, Exception):
                    logger.error(f"Error in fetching keywords: {result}")

            st.session_state.all_keywords.update(valid_keywords)
            st.success(f"Fetched {len(valid_keywords)} keywords.")

    # Fetch SERP results concurrently
    if st.session_state.all_keywords:
        if st.button("Fetch SERP Results"):
            with st.spinner("Fetching SERP results concurrently..."):
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                serp_results = loop.run_until_complete(fetch_serp_results_concurrently(st.session_state.all_keywords))
                st.session_state.serp_results = serp_results
                st.success(f"Fetched SERP results for {len(serp_results)} keywords.")

        # Analyze keywords with Gemini
        if st.session_state.serp_results:
            if st.button("Analyze with Gemini"):
                with st.spinner("Analyzing keywords with Gemini..."):
                    st.session_state.gemini_output = analyze_keywords_with_gemini(st.session_state.all_keywords, st.session_state.serp_results)
                    if st.session_state.gemini_output:
                        st.subheader("Keyword Themes and Groups")
                        st.markdown(st.session_state.gemini_output)
                    else:
                        st.write("No valid SERP results found for analysis.")
        else:
            st.write("No SERP results found.")
    else:
        st.write("No keywords found.")
else:
    st.session_state.all_keywords = set()
    st.session_state.serp_results = {}
    st.session_state.gemini_output = None
