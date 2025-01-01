import streamlit as st
import requests
import string
import time  # For adding delays

# Oxylabs continuous rotation proxy endpoint
PROXY_USER = "customer-kasperpollas_EImZC-cc-us"
PROXY_PASS = "L6mFKak8Uz286dC+"
PROXY_HOST = "pr.oxylabs.io"
PROXY_PORT = "7777"

# Proxy URL (HTTPS)
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"

# Function to fetch Google autosuggest keywords
def get_autosuggest(query):
    url = "https://www.google.com/complete/search"
    params = {
        "q": query,
        "client": "chrome",
    }
    proxies = {
        "http": PROXY_URL,
        "https": PROXY_URL,
    }
    try:
        # Fetch autosuggest keywords
        response = requests.get(url, params=params, proxies=proxies)
        response.raise_for_status()
        return response.json()[1]
    except requests.exceptions.RequestException as e:
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

# Streamlit UI
st.title("Google Autosuggest Keyword Fetcher")
query = st.text_input("Enter a seed keyword:")
if query:
    # Fetch initial autosuggest keywords
    st.write(f"Fetching autosuggest keywords for: {query}")
    initial_keywords = get_autosuggest(query)
    
    # Generate expanded keyword variations
    expanded_keywords = generate_expanded_keywords(query)
    
    # Fetch autosuggest keywords for each expanded variation
    all_keywords = set(initial_keywords)  # Use a set to avoid duplicates
    for expanded_query in expanded_keywords:
        st.write(f"Fetching autosuggest keywords for: {expanded_query}")
        keywords = get_autosuggest(expanded_query)
        if keywords:  # Only add if keywords are fetched successfully
            all_keywords.update(keywords)
        time.sleep(1)  # Add a 1-second delay between requests
    
    # Display the final list of keywords
    if all_keywords:
        st.write("Autosuggest Keywords:")
        for keyword in sorted(all_keywords):  # Sort keywords alphabetically
            st.write(keyword)
    else:
        st.write("No keywords found.")
