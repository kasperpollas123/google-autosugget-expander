import streamlit as st
import requests

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
        st.error(f"Error fetching autosuggest keywords: {e}")
        return []

# Streamlit UI
st.title("Google Autosuggest Keyword Fetcher")
query = st.text_input("Enter a seed keyword:")
if query:
    st.write(f"Fetching autosuggest keywords for: {query}")
    keywords = get_autosuggest(query)
    if keywords:
        st.write("Autosuggest Keywords:")
        for keyword in keywords:
            st.write(keyword)
    else:
        st.write("No keywords found.")
