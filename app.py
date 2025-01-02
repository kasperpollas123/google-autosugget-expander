import streamlit as st
import string
import asyncio
import aiohttp
import pandas as pd
import platform
from aiohttp import ProxyConnector

# Use uvloop for Unix-based systems (Linux, macOS)
if platform.system() != "Windows":
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# Oxylabs continuous rotation proxy endpoint
PROXY_USER = "customer-kasperpollas_EImZC-cc-us"
PROXY_PASS = "L6mFKak8Uz286dC+"
PROXY_HOST = "pr.oxylabs.io"
PROXY_PORT = "7777"

# Proxy URL (HTTPS)
PROXY_URL = f"http://{PROXY_HOST}:{PROXY_PORT}"

# Function to fetch Google autosuggest keywords asynchronously
async def fetch_autosuggest(session, query):
    url = "https://www.google.com/complete/search"
    params = {
        "q": query,
        "client": "chrome",
    }
    try:
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if "application/json" in content_type or "text/javascript" in content_type:
                data = await response.json()
                return data[1]  # Return the list of suggestions
            else:
                st.error(f"Unexpected response format for '{query}': {content_type}")
                return []
    except Exception as e:
        st.error(f"Error fetching autosuggest keywords for '{query}': {e}")
        return []

# Function to generate expanded keyword variations
def generate_expanded_keywords(seed_keyword):
    expanded_keywords = []
    for letter in string.ascii_lowercase:
        # Append letter to the end of the seed keyword
        expanded_keywords.append(f"{seed_keyword} {letter}")
        # Append letter to the beginning of the seed keyword
        expanded_keywords.append(f"{letter} {seed_keyword}")
    return expanded_keywords

# Function to fetch all keywords asynchronously
async def fetch_all_keywords(queries):
    all_keywords = set()
    proxy_auth = aiohttp.BasicAuth(PROXY_USER, PROXY_PASS)
    connector = ProxyConnector(
        proxy=PROXY_URL,
        proxy_auth=proxy_auth,
        limit=150  # Increased concurrency limit to 150
    )
    async with aiohttp.ClientSession(connector=connector) as session:
        for i, query in enumerate(queries):
            keywords = await fetch_autosuggest(session, query)
            if keywords:
                all_keywords.update(keywords)
            if i % 10 == 0:  # Add a delay after every 10 requests
                await asyncio.sleep(1)  # 1-second delay
    return all_keywords

# Streamlit UI
st.title("Google Autosuggest Keyword Fetcher")
query = st.text_input("Enter a seed keyword:")
if query:
    # Initialize variables
    all_keywords = set()

    # Fetch initial autosuggest keywords
    with st.spinner("Fetching initial autosuggest keywords..."):
        async def fetch_initial():
            async with aiohttp.ClientSession() as session:
                return await fetch_autosuggest(session, query)
        initial_keywords = asyncio.run(fetch_initial())
        if initial_keywords:
            all_keywords.update(initial_keywords)

    # Generate expanded keyword variations
    expanded_keywords = generate_expanded_keywords(query)

    # Fetch autosuggest keywords asynchronously
    with st.spinner("Fetching autosuggest keywords asynchronously..."):
        all_keywords.update(asyncio.run(fetch_all_keywords(expanded_keywords)))

    # Display the final list of keywords
    if all_keywords:
        st.success("Keyword fetching completed!")
        st.write(f"Total keywords fetched: {len(all_keywords)}")

        # Convert keywords to a DataFrame
        keywords_df = pd.DataFrame(sorted(all_keywords), columns=["Keyword"])

        # Display the DataFrame
        st.write("Autosuggest Keywords:")
        st.dataframe(keywords_df)

        # Export to CSV
        csv = keywords_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name="autosuggest_keywords.csv",
            mime="text/csv",
        )
    else:
        st.write("No keywords found.")
