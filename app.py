import streamlit as st
import string
import asyncio
import aiohttp
import pandas as pd

# Oxylabs continuous rotation proxy endpoint
PROXY_USER = "customer-kasperpollas_EImZC-cc-us"
PROXY_PASS = "L6mFKak8Uz286dC+"
PROXY_HOST = "pr.oxylabs.io"
PROXY_PORT = "7777"

# Proxy URL (HTTPS)
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# Function to fetch Google autosuggest keywords asynchronously
async def fetch_autosuggest(session, query):
    url = "https://www.google.com/complete/search"
    params = {
        "q": query,
        "client": "chrome",
    }
    proxy_auth = aiohttp.BasicAuth(PROXY_USER, PROXY_PASS)
    try:
        async with session.get(url, params=params, proxy=PROXY_URL, proxy_auth=proxy_auth) as response:
            response.raise_for_status()
            data = await response.json()
            return data[1]  # Return the list of suggestions
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
    connector = aiohttp.TCPConnector(limit=50)  # Increased concurrency limit
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_autosuggest(session, query) for query in queries]
        for i, task in enumerate(asyncio.as_completed(tasks), start=1):
            keywords = await task
            if keywords:
                all_keywords.update(keywords)
            progress_value = i / len(queries)
            progress_bar.progress(min(progress_value, 1.0))
            status_text.text(f"Progress: {i}/{len(queries)} variations completed")
    return all_keywords

# Streamlit UI
st.title("Google Autosuggest Keyword Fetcher")
query = st.text_input("Enter a seed keyword:")
if query:
    # Initialize variables
    all_keywords = set()
    total_variations = 52  # 26 letters * 2 (beginning and end)
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Fetch initial autosuggest keywords
    with st.spinner("Fetching initial autosuggest keywords..."):
        async def fetch_initial():
            async with aiohttp.ClientSession() as session:
                return await fetch_autosuggest(session, query)
        initial_keywords = asyncio.run(fetch_initial())
        if initial_keywords:
            all_keywords.update(initial_keywords)
        progress_value = 1 / total_variations
        progress_bar.progress(min(progress_value, 1.0))  # Ensure progress <= 1
        status_text.text(f"Progress: 1/{total_variations} variations completed")

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
