import streamlit as st
import aiohttp
import asyncio
import string
import logging
from bs4 import BeautifulSoup
from google.api_core import retry
import google.generativeai as genai

# Set up logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Oxylabs proxy endpoint
PROXY_USER = "customer-kasperpollas12345_Lyt6m-cc-us"
PROXY_PASS = "Snaksnak12345+"
PROXY_HOST = "pr.oxylabs.io"
PROXY_PORT = "7777"
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# Google Gemini API key
GEMINI_API_KEY = "AIzaSyAlxm5iSAsNVLbLvIVAAlxFkIBjkjE0E1Y"
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Gemini model (Updated to use Gemini 1.5 Flash)
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# Function to fetch Google autosuggest keywords asynchronously
async def get_autosuggest(query, session, retries=3):
    url = "https://www.google.com/complete/search"
    params = {"q": query, "client": "chrome"}
    for attempt in range(retries):
        try:
            async with session.get(url, params=params, proxy=PROXY_URL, timeout=10) as response:
                response.raise_for_status()
                data = await response.json()
                logger.info(f"Successfully fetched autosuggest for: {query}")
                return data[1]
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"Retrying ({attempt + 1}/{retries}) for '{query}': {e}")
                await asyncio.sleep(1)  # Wait before retrying
            else:
                logger.error(f"Failed to fetch autosuggest for '{query}': {e}")
                return []
    return []

# Function to generate expanded keyword variations
def generate_expanded_keywords(seed_keyword):
    expanded_keywords = []
    for letter in string.ascii_lowercase:
        expanded_keywords.append(f"{seed_keyword} {letter}")
        expanded_keywords.append(f"{letter} {seed_keyword}")
    return expanded_keywords

# Function to fetch keywords concurrently using asyncio
async def fetch_keywords_concurrently(queries):
    semaphore = asyncio.Semaphore(50)  # Reduce concurrency to avoid rate-limiting
    async with aiohttp.ClientSession() as session:
        tasks = []
        for query in queries:
            async with semaphore:
                task = asyncio.create_task(get_autosuggest(query, session))
                tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

# Function to fetch and parse Google SERP asynchronously
async def fetch_google_serp(query, session, limit=5, retries=3):
    url = f"https://www.google.com/search?q={query}"
    for attempt in range(retries):
        try:
            async with session.get(url, proxy=PROXY_URL, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')
                    results = []
                    for result in soup.find_all('div', class_='Gx5Zad xpd EtOod pkphOe')[:limit]:
                        if "ads" in result.get("class", []):
                            continue
                        title_element = result.find('h3') or result.find('h2') or result.find('div', class_='BNeawe vvjwJb AP7Wnd')
                        title = title_element.get_text().strip() if title_element else "No Title Found"
                        description_element = result.find('div', class_='BNeawe s3v9rd AP7Wnd') or \
                                             result.find('div', class_='v9i61e') or \
                                             result.find('div', class_='BNeawe UPmit AP7Wnd lRVwie') or \
                                             result.find('div', class_='BNeawe s3v9rd AP7Wnd')
                        description = description_element.get_text().strip() if description_element else "No Description Found"
                        results.append({
                            "title": title,
                            "description": description
                        })
                    logger.info(f"Successfully fetched SERP for: {query}")
                    return results
                elif response.status == 429:  # Rate limit exceeded
                    logger.warning(f"Rate limit exceeded for '{query}'. Retrying ({attempt + 1}/{retries})...")
                    await asyncio.sleep(10)  # Wait before retrying
                else:
                    logger.error(f"Error fetching SERP for '{query}': Status code {response.status}")
                    return f"Error: Status code {response.status}"
        except Exception as e:
            logger.error(f"Error fetching SERP for '{query}': {e}")
            if attempt < retries - 1:
                await asyncio.sleep(5)  # Wait before retrying
            else:
                return f"Error: {e}"
    return f"Error: Max retries reached for '{query}'."

# Function to fetch SERP results concurrently using asyncio
async def fetch_serp_results_concurrently(keywords):
    semaphore = asyncio.Semaphore(50)  # Reduce concurrency to avoid rate-limiting
    async with aiohttp.ClientSession() as session:
        tasks = []
        for keyword in keywords:
            async with semaphore:
                task = asyncio.create_task(fetch_google_serp(keyword, session))
                tasks.append(task)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return dict(zip(keywords, results))

# Function to analyze keywords with Gemini
def analyze_keywords_with_gemini(keywords, serp_results):
    prompt = """
    Please analyse the intent for all of the keywords on this list based on the SERP page results for each keyword. Then come up with different themes that keywords can be grouped under. You may use the same keyword more than once in different themes but only once in each theme. The themes should have a catchy and inspiring headline and underneath the headline should simply be the keywords that are grouped together. For each group please remove and omit keywords that are too similar to other keywords and basically mean the same thing and reflect the same intent like for example 'my cat peeing everywhere' and 'cat is peeing everywhere'. You are not allowed to make up keywords that are not on the list i give you. Please limit each group to a maximum of 20 keywords. If there are any keywords that stick out as weird for example asking for the keyword in a specific language or if they just stick out to much compared to the overall intent of most of the keywords, then please remove them.

    The final output should look EXACTLY like this:

    Finding Local Plumbing Professionals
    - r plumbing company
    - j plumbing chicago
    - z plumbers livonia
    - r plumber llc
    - r plumbing
    - j.p. plumbing
    - z plumbing and heating
    - r plumbing llc reviews

    Generating Plumbing Leads
    - plumbing lead generation agency fatrank
    - plumber lead generation
    - how to get plumbing leads
    - plumbing lead generation james dooley
    - plumbing lead generation services
    - plumbing leads near me
    - plumbing leads for plumbers
    - plumbing lead generation services fatrank
    - plumbing lead generation company james dooley
    - plumbing lead generation

    Understanding Lead Pipes in Plumbing
    - lead plumbing pipe
    - plumbing lead
    - plumbing lead joint
    - lead plumbing
    - plumbing lead pipes
    - lead plumbing history
    - led plumbing
    - is lead still used in plumbing
    - how much to replace lead plumbing
    - who is responsible for replacing lead water pipes

    Plumbing Tools and Equipment
    - plumbing lead tools
    - plumbing lead melting pot

    Plumbing Job Information
    - lead plumber salary
    - lead plumber job description

    Do not include any explanations, notes, or additional text. Only provide the grouped keywords in the specified format. The format must be EXACTLY as shown above, with no deviations.
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
        st.error(f"Error calling Gemini API: {e}")
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
    with st.spinner("Fetching autosuggest keywords concurrently..."):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(fetch_keywords_concurrently(expanded_keywords))

        # Filter out exceptions and ensure only valid lists are processed
        valid_keywords = []
        for result in results:
            if isinstance(result, list):  # Only process valid results
                valid_keywords.extend(result)
            elif isinstance(result, Exception):  # Log errors
                logger.error(f"Error in fetching keywords: {result}")

        # Update session state with valid keywords
        st.session_state.all_keywords.update(valid_keywords)

    # Fetch SERP results concurrently
    if st.session_state.all_keywords:
        with st.spinner("Fetching SERP results concurrently..."):
            serp_results = loop.run_until_complete(fetch_serp_results_concurrently(st.session_state.all_keywords))
            st.session_state.serp_results = serp_results

        # Analyze keywords with Gemini
        if st.session_state.serp_results:
            with st.spinner("Analyzing keywords with Gemini..."):
                st.session_state.gemini_output = analyze_keywords_with_gemini(st.session_state.all_keywords, st.session_state.serp_results)

        # Display Gemini output
        if st.session_state.gemini_output:
            st.subheader("Keyword Themes and Groups")
            st.markdown(st.session_state.gemini_output)
        else:
            st.write("No valid SERP results found for analysis.")
    else:
        st.write("No keywords found.")
else:
    st.session_state.all_keywords = set()
    st.session_state.serp_results = {}
    st.session_state.gemini_output = None
