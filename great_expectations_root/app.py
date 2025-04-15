import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import time
import random
import webbrowser
import ollama
import json
import os
import re
from helpers.utils import * 
from connecting_data.database.postgresql import *
from connecting_data.filesystem.pandas_filesystem import *
from streamlit_extras.dataframe_explorer import dataframe_explorer
from streamlit_extras.no_default_selectbox import selectbox

def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

def remote_css(url):
    st.markdown(f'<link href="{url}" rel="stylesheet">', unsafe_allow_html=True)

# Define valid Great Expectations expectation types for validation
VALID_EXPECTATION_TYPES = [
    # Column expectations
    "expect_column_values_to_be_null",
    "expect_column_values_to_not_be_null",
    "expect_column_values_to_be_in_set",
    "expect_column_values_to_not_be_in_set",
    "expect_column_values_to_be_between",
    "expect_column_values_to_be_increasing",
    "expect_column_values_to_be_decreasing",
    "expect_column_values_to_match_regex",
    "expect_column_values_to_match_regex_list",
    "expect_column_values_to_match_strftime_format",
    "expect_column_values_to_be_dateutil_parseable",
    "expect_column_values_to_be_json_parseable",
    "expect_column_values_to_match_json_schema",
    "expect_column_distinct_values_to_be_in_set",
    "expect_column_distinct_values_to_contain_set",
    "expect_column_distinct_values_to_equal_set",
    "expect_column_mean_to_be_between",
    "expect_column_median_to_be_between",
    "expect_column_quantile_values_to_be_between",
    "expect_column_stdev_to_be_between",
    "expect_column_unique_value_count_to_be_between",
    "expect_column_proportion_of_unique_values_to_be_between",
    "expect_column_most_common_value_to_be_in_set",
    "expect_column_sum_to_be_between",
    "expect_column_min_to_be_between",
    "expect_column_max_to_be_between",
    "expect_column_value_lengths_to_be_between",
    "expect_column_value_lengths_to_equal",
    "expect_column_values_to_be_unique",
    "expect_column_values_to_not_be_null",
    # Table expectations
    "expect_table_row_count_to_be_between",
    "expect_table_row_count_to_equal",
    "expect_table_column_count_to_be_between",
    "expect_table_column_count_to_equal",
    "expect_table_columns_to_match_ordered_list",
    "expect_table_columns_to_match_set"
]

# Use the absolute path to the data directory
local_filesystem_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data/')
print(f"Data path: {local_filesystem_path}")
session_state = st.session_state

#data_owner_button_key = "data_owner_button_1"

st.set_page_config(
    page_title="AI Data Doctor",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)  
st.title("🩺 AI Data Doctor")
st.markdown('<h1 style="font-size: 24px; font-weight: bold; margin-bottom: 0;">Welcome to your Data Doctor App</h1>', unsafe_allow_html=True)

# Display the sidebar content
st.sidebar.markdown("""
# Data Quality Checks

This app allows you to perform data quality checks on your data sources using Great Expectations.

## Features
- Connect to local filesystem data
- Connect to PostgreSQL databases
- Generate data quality expectations using AI
- View data quality results
- Contact data owners

## How to Use
1. Select your data source (Local File System or PostgreSQL)
2. Choose a table or file
3. Describe the data quality checks you want to perform
4. View the results
5. Contact the data owner if needed

## Data Sources
- Local File System: CSV files in the data directory
- PostgreSQL: Tables in your database
""", unsafe_allow_html=True)

def display_data_preview(data):
    """
    Display data for quick data exploration
    Params:
        data (DataFrame) : Selected table on which to run DQ checks    
    """
    try:
        filtered_df = dataframe_explorer(data, case=False)
        st.dataframe(filtered_df, use_container_width=True)
    except:
        raise Exception("Unable to preview data")

def display_test_result(result_dict):
    """
    Display the results of a Great Expectations test in a user-friendly format
    """
    # Extract relevant information
    success = result_dict.get('success', False)
    result_type = result_dict.get('expectation_config', {}).get('expectation_type', 'Unknown Test')
    
    # Display overall result with appropriate styling
    if success:
        st.success(f"✅ Test Passed: {result_type}")
    else:
        st.error(f"❌ Test Failed: {result_type}")
    
    # Create tabs for different sections of the results
    test_params, result_details, errors = st.tabs(["Test Parameters", "Result Details", "Errors"])
    
    with test_params:
        # Show the test parameters
        kwargs = result_dict.get('expectation_config', {}).get('kwargs', {})
        for key, value in kwargs.items():
            st.write(f"- {key}: {value}")
    
    with result_details:
        # Show the result details
        result = result_dict.get('result', {})
        
        # Remove internal keys for cleaner display
        keys_to_show = [k for k in result.keys() if not k.startswith('_')]
        for key in keys_to_show:
            value = result[key]
            if isinstance(value, (int, float)):
                # Format numbers nicely
                st.write(f"- {key}: {value:,}")
            else:
                st.write(f"- {key}: {value}")
        
        # Show observed value if available
        if 'observed_value' in result:
            st.subheader("Observed Value")
            st.write(result['observed_value'])
    
    with errors:
        # Show any exceptions or unexpected issues
        if 'exception_info' in result_dict:
            st.error(result_dict['exception_info'].get('exception_message', 'Unknown error occurred'))
        else:
            st.write("No errors reported.")

def perform_data_quality_checks(DQ_APP, key):
    """
    Function to perform data quality checks using Ollama
    Params:
        DQ_APP (object) : Instanciated class for data quality checks
                          (Data sources : PostgreSQL, Filesystem, etc.)
    """
    st.subheader("Perform Data Quality Checks")
    
    checks_input = st.text_area("Describe the checks you want to perform", key=key.format(name='check_input'),
                                placeholder="Example: 'Column price should be between 0 and 2000.' or 'Column status must be one of [COMPLETED, PENDING, SHIPPED]'. Ensure column names match the data.")

    if checks_input:
        submit_button = st.button("Submit", key=key.format(name='submit'))
        if submit_button:
            with st.spinner('Generating expectation and running checks with Ollama...'):
                try:
                    # --- Ollama Integration ---
                    system_prompt = ("""You are an expert in Great Expectations. Your task is to convert the user's natural language description of a data quality check into a single Great Expectations Expectation JSON object. 

ONLY output the JSON object, nothing else. The JSON should be compatible with the Great Expectations `run_expectation` method. Focus on creating ONE expectation per request.

IMPORTANT JSON formatting:
- Use valid JSON format with double quotes for strings and property names
- For missing or unlimited values, use 'null' (not None, undefined, or empty string)
- For example: {"max_value": null} not {"max_value": None}

IMPORTANT Regex Guidelines:
- Use expect_column_values_to_match_regex only for text pattern matching
- For numeric columns, use expect_column_values_to_be_between or other numeric expectations
- Regex patterns must be valid PostgreSQL regular expressions

Available tables and their columns:
1. PostgreSQL Tables:
   - customers: customer_id (int), first_name (text), last_name (text), email (text), phone (text), address (text), created_at (timestamp), updated_at (timestamp)
   - products: product_id (int), name (text), description (text), price (decimal), stock_quantity (int), created_at (timestamp), updated_at (timestamp)
   - orders: order_id (int), customer_id (int), order_date (timestamp), total_amount (decimal), status (text), created_at (timestamp), updated_at (timestamp)
   - order_items: order_item_id (int), order_id (int), product_id (int), quantity (int), unit_price (decimal), created_at (timestamp), updated_at (timestamp)

2. CSV Files:
   - Housing: id (int), address (text), city (text), state (text), zip (text), price (int), bedrooms (int), bathrooms (float), sqft (int), year_built (int), property_type (text)
   - SupermarketSales: [sales data]
   - Users: [user data]

IMPORTANT: Use ONLY these valid expectation types:
- expect_column_values_to_be_between
- expect_column_values_to_be_in_set
- expect_column_values_to_not_be_null
- expect_column_values_to_be_null
- expect_column_values_to_be_unique
- expect_column_values_to_match_regex (use only for text columns)
- expect_table_row_count_to_be_between
- expect_column_mean_to_be_between
- expect_column_min_to_be_between
- expect_column_max_to_be_between
- expect_column_sum_to_be_between
- expect_column_proportion_of_unique_values_to_be_between

Example user input: 'Column price should be between 0 and 2000000.'
Example JSON output: {"expectation_type": "expect_column_values_to_be_between", "kwargs": {"column": "price", "min_value": 0, "max_value": 2000000}}

Example user input: 'Column price should be greater than 0.'
Example JSON output: {"expectation_type": "expect_column_values_to_be_between", "kwargs": {"column": "price", "min_value": 0, "max_value": null}}

Example user input: 'Column status must be one of [COMPLETED, PENDING, SHIPPED]'
Example JSON output: {"expectation_type": "expect_column_values_to_be_in_set", "kwargs": {"column": "status", "value_set": ["COMPLETED", "PENDING", "SHIPPED"]}}

Example user input: 'Column email should match email format'
Example JSON output: {"expectation_type": "expect_column_values_to_match_regex", "kwargs": {"column": "email", "regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"}}

Make sure to format the JSON correctly and use the exact expectation names as listed above.""")

                    response = ollama.chat(
                        model='phi4-mini', # Using phi4-mini as requested
                        messages=[
                            {'role': 'system', 'content': system_prompt},
                            {'role': 'user', 'content': checks_input}
                        ]
                    )

                    ollama_response_content = response['message']['content'].strip()
                    
                    # Attempt to find JSON within potential markdown code blocks
                    if ollama_response_content.startswith("```json"):
                        ollama_response_content = ollama_response_content[7:]
                    elif ollama_response_content.startswith("```"):
                        ollama_response_content = ollama_response_content[3:]
                    
                    if ollama_response_content.endswith("```"):
                        ollama_response_content = ollama_response_content[:-3]
                    
                    # Clean up the response to ensure it's valid JSON
                    ollama_response_content = ollama_response_content.strip()
                    
                    # Fix Python None -> JSON null conversion
                    ollama_response_content = ollama_response_content.replace(": None", ": null")
                    ollama_response_content = ollama_response_content.replace(":None", ":null")
                    
                    # Debug the raw response
                    st.write("Raw Ollama Response:")
                    st.code(ollama_response_content, language='json')
                    
                    try:
                        # Parse the JSON response
                        expectation_json = json.loads(ollama_response_content)
                    except json.JSONDecodeError:
                        # Try a different approach - extract JSON using regex
                        json_pattern = r'\{.*\}'
                        match = re.search(json_pattern, ollama_response_content, re.DOTALL)
                        if match:
                            json_str = match.group(0)
                            expectation_json = json.loads(json_str)
                        else:
                            raise
                    
                    # Validate that the expectation type is valid
                    expectation_type = expectation_json.get('expectation_type')
                    if expectation_type not in VALID_EXPECTATION_TYPES:
                        st.error(f"Invalid expectation type: {expectation_type}")
                        st.warning(f"Please use one of the valid expectation types: {', '.join(VALID_EXPECTATION_TYPES[:5])}...")
                        return

                    st.write("Generated Expectation:")
                    st.json(expectation_json) # Show the generated JSON

                    expectation_result = DQ_APP.run_expectation(expectation_json)
                    st.success('Your test has successfully been run! See results below.')
                    with st.expander("Show Results"):
                        st.subheader("Data Quality result")
                        display_test_result(expectation_result.to_json_dict())
                
                except json.JSONDecodeError as json_err:
                     st.error(f"Error parsing JSON response from Ollama: {json_err}")
                     st.text_area("Ollama Response (raw):", ollama_response_content, height=150)
                except ollama.ResponseError as ollama_err:
                    st.error(f"Error communicating with Ollama: {ollama_err}. Is Ollama running and the model 'phi4-mini' pulled?")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
                    st.warning("This might happen if the generated expectation is invalid for the data, the column name is misspelled, or Ollama didn't produce valid JSON.")

def open_data_docs(DQ_APP, key):
    """
    Open expectation data docs (great expection html output)
    Params:
        DQ_APP (object) : Instanciated class for data quality checks
                          (Data sources : PostgreSQL, Filesystem, etc.)
    """

    open_docs_button = st.button("Open Data Docs", key=key.format(name='data_docs'))
    if open_docs_button:
        try:
            data_docs_url = DQ_APP.context.get_docs_sites_urls()[0]['site_url']
            st.write(data_docs_url)
            webbrowser.open_new_tab(data_docs_url)
        except:
            st.warning('Unable to open html report. Ensure that you have great_expectations/uncommited folder with validations and data_docs/local_site subfolders.', icon="⚠️")



def contact_data_owner(session_state, data_owners, data_source, key):
    """
    Function to contact data owner
    Params:
        session_state : Current session state
        data_owners (dict) : Contains data sources (tables) as dict keys and the data owner email for each data source
        data_source (str) : Selected data source by user on which they want to run data quality checks
    """
    try:
        if session_state['page'] == 'home':
            data_owner_button = st.button("Contact Data Owner", key=key.format(name='do'))
            if data_owner_button:
                session_state['page'] = 'contact_form'

        if session_state['page'] == 'contact_form':
            st.header("Contact Form")
            sender_email = "aidatadoctor@gmail.com"
            recipient_email = st.text_input("Recipient Email", value=data_owners[data_source])
            subject = st.text_input("Subject", key=key.format(name='subject'))
            message = st.text_area("Message", key=key.format(name='message'))
            attachement = "great_expectations/uncommitted/data_docs/local_site/index.html"
                
            if st.button("Send Email", key=key.format(name='email')):
                send_email_with_attachment(sender_email, recipient_email, subject, message, attachement)
                session_state['page'] = 'email_sent'

        if session_state['page'] == 'email_sent':
            session_state['page'] = 'home'
    except:
        st.warning('Unable to send email. Verify the email setup.', icon="⚠️")

def next_steps(DQ_APP, data_owners, data_source, key):
    """
    Actions to take after running data quality checks
    View expectation data docs
    Contact Data Owner by email with data docs as attachment
    """
    st.subheader("What's next ?")
    t1,t2 = st.tabs(['Expectation Data Docs','Get in touch with Data Owner']) 
    with t1:
        open_data_docs(DQ_APP, key)
    with t2:           
        contact_data_owner(session_state, data_owners, data_source, key)


def main():
    # Set the app title
    DQ_APP = None  
    data_owners = None
    data_source = None

    if 'page' not in session_state:
        session_state['page'] = 'home'

    # Select the data connection
    t1,t2 = st.tabs(['Local File System','PostgreSQL']) 

    with t1:
        mapping, data_owners = local_dataowners(local_filesystem_path)
        tables = list(mapping.keys())
        data_source = selectbox("Select table name", tables)

        if data_source:
            key = "filesystem_{name}"
            # Display a preview of the data
            st.subheader("Preview of the data:")
            data = read_local_filesystem_tb(local_filesystem_path, data_source, mapping)
            display_data_preview(data)

            DQ_APP = PandasFilesystemDatasource(data_source, data)
            perform_data_quality_checks(DQ_APP, key)
            next_steps(DQ_APP, data_owners, data_source, key)

    with t2:
        try:
            data_owners = postgresql_data_owners()
            tables = get_pg_tables()
            data_source = selectbox("Select PostgreSQL table", tables)
            if data_source:
                key = "postgresql_{name}"
                # Display a preview of the data
                st.subheader("Preview of the data:")
                data = read_pg_tables(data_source)
                display_data_preview(data)
        
                DQ_APP = PostgreSQLDatasource('gdpr_fines', data_source)
                perform_data_quality_checks(DQ_APP, key)
                next_steps(DQ_APP, data_owners, data_source, key)
        except:
            st.warning('Unable to connect to Postgresql. Please verify that you have added your connection string in .env file', icon="⚠️")
            Exception("PostgreSQL Connection error")

 
local_css("ui/front.css")
remote_css('https://fonts.googleapis.com/icon?family=Material+Icons')
remote_css('https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@300;400;500;600;700&display=swap')
# Run the app
if __name__ == "__main__":
    main()
