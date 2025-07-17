import requests
import os
import json
import sys
import base64
import re

def get_bearer_token(token_url, client_id, client_secret, scope):
    """
    Fetches an OAuth 2.0 Bearer Token using the Client Credentials Grant type.
    """
    print("\n--- Attempting to fetch Bearer Token ---")
    print(f"Token URL: {token_url}")

    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    payload = f'grant_type=client_credentials&scope={scope}'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {encoded_credentials}'
    }

    response = None
    try:
        print(f"Request Payload: {payload}")
        print(f"Request Headers (partial): {{'Content-Type': '{headers['Content-Type']}', 'Authorization': 'Basic ...'}}")

        response = requests.post(token_url, headers=headers, data=payload, verify=True, timeout=30)
        response.raise_for_status()

        if response.status_code == 204:
            print("Warning: Token endpoint returned 204 No Content. No token received.")
            return None

        token_response = response.json()
        print(f"Token API Response (JSON): {json.dumps(token_response, indent=2)}")

        bearer_token = token_response.get("access_token")
        if bearer_token:
            print("Successfully fetched Bearer Token.")
            return bearer_token
        else:
            print("Error: 'access_token' not found in the token response.")
            if response:
                print(f"Raw Token Response Text: {response.text}")
            return None

    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error fetching token: {e}")
        if e.response is not None:
            print(f"Response Status Code: {e.response.status_code}")
            print(f"Response Content: {e.response.text}")
        print("Please check your token URL, client ID, client secret, and scope.")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"Connection Error fetching token: {e}")
        print("Please check the token URL and network connectivity.")
        return None
    except requests.exceptions.Timeout as e:
        print(f"Timeout Error fetching token: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"An unexpected request error occurred while fetching token: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Raw Response Text (on generic error): {e.response.text}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON response from token endpoint. Details: {e}")
        print(f"Raw Token Response Text (on JSONDecodeError):")
        print("--- START RAW RESPONSE (TOKEN) ---")
        if response:
            print(response.text)
        else:
            print("No response object available.")
        print("--- END RAW RESPONSE (TOKEN) ---")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while fetching token: {e}")
        return None

def derive_integration_id_from_filename(filename_with_ext):
    """
    Derives the integration ID (CODE|VERSION) from a filename.
    Assumes filename format like 'CODE|XX.YY.ZZZZ.iar', 'CODE_XX_YY_ZZZZ.iar',
    or 'CODE-vX-Y-Z.iar'. It prioritizes finding a version pattern at the end.
    """
    filename_without_ext = filename_with_ext.replace(".iar", "")

    # 1. Check if it's already in CODE|VERSION format (most direct and preferred)
    if '|' in filename_without_ext:
        print(f"  Info: Filename '{filename_with_ext}' already in CODE|VERSION format.")
        return filename_without_ext

    # 2. Attempt to extract version from the end of the filename
    version_pattern = r'([._-])?([vV]?\d+(?:[._-]\d+){1,3})$'
    match = re.search(version_pattern, filename_without_ext)

    if match:
        version_str = match.group(2)
        code_part = filename_without_ext[:match.start(2) - (1 if match.group(1) else 0)]
        
        cleaned_version = version_str.lstrip('vV').replace('_', '.').replace('-', '.')
        code_part = code_part.rstrip('._-')

        print(f"  Info: Filename '{filename_with_ext}' parsed as Code: '{code_part}', Version: '{cleaned_version}'.")
        return f"{code_part}|{cleaned_version}"
    
    # 3. Fallback: If no specific version pattern is found, just use the filename as code.
    print(f"  Warning: Could not parse specific CODE|VERSION pattern from filename '{filename_with_ext}'.")
    print(f"  Defaulting to filename without extension as the integration ID: '{filename_without_ext}'.")
    print(f"  Activation might fail if OIC requires a 'CODE|VERSION' format and the filename doesn't contain a parseable version.")
    return filename_without_ext


def deploy_oic_integration(oic_url, bearer_token, iar_file_path, instance_name=None, enable_async_activation_mode=False):
    """
    Deploys a single Oracle Integration Cloud (.iar) file using a Bearer Token for authentication.
    Optionally targets a specific integration instance during import and activation,
    and uses PATCH method override for activation.
    Handles 204 No Content for import by deriving integration ID from filename.
    """

    base_api_url = oic_url
    if not base_api_url.endswith("/ic/api/integration/v1"):
        base_api_url = os.path.join(oic_url, "ic/api/integration/v1")

    import_url = f"{base_api_url}/integrations/archive"
    if instance_name:
        import_url += f"?integrationInstance={instance_name}"
        print(f"  Import URL modified to target instance: {instance_name}")

    activate_base_url = f"{base_api_url}/integrations/{{integration_id}}"

    common_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}"
    }

    print(f"\n--- Attempting deployment for: {os.path.basename(iar_file_path)} ---")

    response = None
    integration_id = None

    try:
        if not os.path.exists(iar_file_path):
            print(f"Error: The IAR file '{iar_file_path}' was not found. Skipping.")
            return False

        print(f"  Step 1/2: Importing integration from '{os.path.basename(iar_file_path)}'...")
        print(f"  Using Import URL: {import_url}")
        with open(iar_file_path, 'rb') as iar_file:
            files = {'file': (os.path.basename(iar_file_path), iar_file, 'application/octet-stream')}
            
            response = requests.post(import_url, files=files, headers=common_headers, verify=True, timeout=60)
            response.raise_for_status()

        if response.status_code == 204:
            print(f"  Import for '{os.path.basename(iar_file_path)}' returned 204 No Content (considered success).")
            integration_id = derive_integration_id_from_filename(os.path.basename(iar_file_path))
            
        else:
            try:
                import_result = response.json()
                print(f"  Import API Response (JSON): {json.dumps(import_result, indent=2)}")

                if import_result.get("status") == "SUCCESS":
                    integration_id = import_result.get("id")
                    if not integration_id:
                        print("  Error: 'id' not found in import response despite 'SUCCESS' status.")
                        integration_id = derive_integration_id_from_filename(os.path.basename(iar_file_path))
                        print(f"  Attempting to derive ID from filename instead: '{integration_id}'")
                        
                        if response:
                            print(f"  Raw Import Response Text: {response.text}")
                    else:
                        print(f"  Successfully imported integration. ID (CODE|VERSION): '{integration_id}'.")
                else:
                    error_message = import_result.get('message', 'Unknown error during import.')
                    print(f"  Error importing integration: {error_message}")
                    if response:
                        print(f"  Raw Import Response Text: {response.text}")
                    return False
            except json.JSONDecodeError as e:
                print(f"  Error: Failed to parse JSON response from OIC API (Import step). Details: {e}")
                print(f"  Raw OIC API Response Text (on JSONDecodeError):")
                print("  --- START RAW RESPONSE (OIC IMPORT API) ---")
                if response:
                    print(response.text)
                else:
                    print("  No response object available.")
                print("  --- END RAW RESPONSE (OIC IMPORT API) ---")
                integration_id = derive_integration_id_from_filename(os.path.basename(iar_file_path))
                print(f"  Attempting to derive ID from filename instead due to JSON parsing error: '{integration_id}'")

        if not integration_id:
            print("  Cannot proceed to activation: Integration ID could not be determined from import response or filename.")
            return False

        # --- Construct Activation URL with Query Parameters ---
        activate_url = activate_base_url.format(integration_id=integration_id)
        query_params = []
        if instance_name:
            query_params.append(f"integrationInstance={instance_name}")
        if enable_async_activation_mode:
            query_params.append("enableAsyncActivationMode=true")
        
        if query_params:
            activate_url += "?" + "&".join(query_params)
        # --- End Activation URL Construction ---

        print(f"  Step 2/2: Activating integration '{integration_id}'...")
        print(f"  Using Activation URL: {activate_url}")

        activate_payload = {
            "status": "ACTIVATED"
        }
        
        activate_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {bearer_token}",
            "X-HTTP-Method-Override": "PATCH"
        }

        response = requests.request("POST", activate_url, headers=activate_headers, json=activate_payload, verify=True, timeout=60)
        
        # --- NEW: Consider 200 OK or specific statuses as success for Activation ---
        if response.status_code == 200:
            try:
                activate_result = response.json()
                print(f"  Activation API Response (JSON): {json.dumps(activate_result, indent=2)}")
                
                # Check for ACTIVATED or ACTIVATION_INPROGRESS
                if activate_result.get("status") in ["ACTIVATED", "ACTIVATION_INPROGRESS"]:
                    print(f"  Integration '{integration_id}' activation initiated/completed successfully (Status 200 and '{activate_result.get('status')}').")
                    return True
                else:
                    error_message = activate_result.get('message', 'Unknown error during activation.')
                    print(f"  Error activating integration '{integration_id}': {error_message} (Status 200 but unexpected internal status '{activate_result.get('status')}').")
                    if response:
                        print(f"  Raw Activation Response Text: {response.text}")
                    return False
            except json.JSONDecodeError as e:
                print(f"  Error: Failed to parse JSON response from OIC API (Activation step - Status 200). Details: {e}")
                print(f"  Raw OIC API Response Text (on JSONDecodeError):")
                print("  --- START RAW RESPONSE (OIC ACTIVATION API) ---")
                if response:
                    print(response.text)
                else:
                    print("  No response object available.")
                print("  --- END RAW RESPONSE (OIC ACTIVATION API) ---")
                print(f"  Integration '{integration_id}' activation might have succeeded (Status 200), but response was not JSON.")
                return True # Consider 200 OK a success even if JSON is malformed
        else:
            response.raise_for_status() # Raise for any other non-200, non-204 status codes
            print(f"  Unexpected status code for activation: {response.status_code}. Assuming failure.")
            if response:
                print(f"  Raw Activation Response Text: {response.text}")
            return False
        # --- END NEW Activation Handling ---

    except requests.exceptions.HTTPError as e:
        print(f"  HTTP Error during deployment: {e}")
        if e.response is not None:
            print(f"  Response Status Code: {e.response.status_code}")
            print(f"  Response Content: {e.response.text}")
        if e.response.status_code == 401:
            print("  Authentication failed! Please check your Bearer Token validity or OIC instance configuration.")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"  Connection Error: Could not connect to OIC instance. Please check URL and network connectivity. Error: {e}")
        return False
    except requests.exceptions.Timeout as e:
        print(f"  Timeout Error: Request to OIC instance timed out. Error: {e}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  An unexpected request error occurred: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Raw Response Text (on generic error): {e.response.text}")
        return False
    except json.JSONDecodeError as e: # This should now primarily catch errors from Activation step if it returns non-JSON
        print(f"  Error: Failed to parse JSON response from OIC API (Activation step). Details: {e}")
        print(f"  Raw OIC API Response Text (on JSONDecodeError):")
        print("  --- START RAW RESPONSE (OIC ACTIVATION API) ---")
        if response:
            print(response.text)
        else:
            print("  No response object available.")
        print("  --- END RAW RESPONSE (OIC ACTIVATION API) ---")
        return False
    except Exception as e:
        print(f"  An unexpected error occurred: {e}")
        return False

if __name__ == "__main__":
    # --- Configuration ---
    OIC_URL = os.environ.get("OIC_URL")
    IAR_FILES_INPUT = os.environ.get("IAR_FILES")

    # OAuth Client Credentials for Token Fetching
    OIC_TOKEN_URL = os.environ.get("OIC_TOKEN_URL")
    OIC_CLIENT_ID = os.environ.get("OIC_CLIENT_ID")
    OIC_CLIENT_SECRET = os.environ.get("OIC_CLIENT_SECRET")
    OIC_SCOPE = os.environ.get("OIC_SCOPE")

    # Optional Integration Instance Name (used in both import and activate URLs)
    OIC_INSTANCE_NAME = os.environ.get("OIC_INSTANCE_NAME")

    # Enable Async Activation Mode (boolean, e.g., "true" or "false")
    OIC_ENABLE_ASYNC_ACTIVATION = os.environ.get("OIC_ENABLE_ASYNC_ACTIVATION", "false").lower() == "true"

    # Fallback Bearer Token (for when automatic fetching fails)
    OIC_FALLBACK_BEARER_TOKEN = os.environ.get("OIC_FALLBACK_BEARER_TOKEN")


    # --- Validate Core Configuration ---
    if not OIC_URL:
        print("Error: OIC_URL environment variable is not set.")
        sys.exit(1)
    if not IAR_FILES_INPUT:
        print("Error: IAR_FILES environment variable is not set. Please provide file paths or a directory.")
        sys.exit(1)

    # Validate token fetching credentials, but allow fallback
    if not all([OIC_TOKEN_URL, OIC_CLIENT_ID, OIC_CLIENT_SECRET, OIC_SCOPE]):
        if not OIC_FALLBACK_BEARER_TOKEN:
            print("Error: OAuth token fetching credentials (OIC_TOKEN_URL, OIC_CLIENT_ID, OIC_CLIENT_SECRET, OIC_SCOPE) are not fully set, and no OIC_FALLBACK_BEARER_TOKEN is provided.")
            sys.exit(1)
        else:
            print("Warning: OAuth token fetching credentials are incomplete. Will attempt to use OIC_FALLBACK_BEARER_TOKEN if token fetching fails.")

    # --- Fetch Bearer Token ---
    bearer_token = None
    if all([OIC_TOKEN_URL, OIC_CLIENT_ID, OIC_CLIENT_SECRET, OIC_SCOPE]):
        bearer_token = get_bearer_token(OIC_TOKEN_URL, OIC_CLIENT_ID, OIC_CLIENT_SECRET, OIC_SCOPE)
    else:
        print("Skipping automatic token fetching due to incomplete credentials.")

    if not bearer_token:
        if OIC_FALLBACK_BEARER_TOKEN:
            print("\nAutomatic token fetching failed or skipped. Attempting to use OIC_FALLBACK_BEARER_TOKEN.")
            bearer_token = OIC_FALLBACK_BEARER_TOKEN
        else:
            print("\nFailed to obtain Bearer Token, and no fallback token provided. Exiting deployment.")
            sys.exit(1)

    # --- Determine files to deploy ---
    files_to_deploy = []
    if os.path.isdir(IAR_FILES_INPUT):
        print(f"\nIAR_FILES is a directory: '{IAR_FILES_INPUT}'. Searching for .iar files...")
        for root, _, files in os.walk(IAR_FILES_INPUT):
            for file in files:
                if file.endswith(".iar"):
                    files_to_deploy.append(os.path.join(root, file))
        if not files_to_deploy:
            print(f"No .iar files found in directory: '{IAR_FILES_INPUT}'.")
            sys.exit(1)
    else:
        print(f"\nIAR_FILES is a list of files. Parsing: '{IAR_FILES_INPUT}'")
        files_to_deploy = [f.strip() for f in IAR_FILES_INPUT.split(',') if f.strip()]
        if not files_to_deploy:
            print("No valid .iar file paths found in IAR_FILES environment variable.")
            sys.exit(1)

    print(f"\nFound {len(files_to_deploy)} .iar file(s) for deployment:")
    for f in files_to_deploy:
        print(f"  - {f}")

    # --- Execute Deployment for each file ---
    overall_success = True
    deployment_results = {}

    for iar_file in files_to_deploy:
        file_basename = os.path.basename(iar_file)
        success = deploy_oic_integration(OIC_URL, bearer_token, iar_file, OIC_INSTANCE_NAME, OIC_ENABLE_ASYNC_ACTIVATION)
        deployment_results[file_basename] = "SUCCESS" if success else "FAILED"
        if not success:
            overall_success = False

    # --- Print Summary ---
    print("\n" + "="*50)
    print("Deployment Summary:")
    print("="*50)
    for file_name, status in deployment_results.items():
        print(f"  {file_name}: {status}")
    print("="*50)

    if not overall_success:
        print("\nOne or more integrations failed to deploy or activate. Please review the logs above for details.")
        sys.exit(1)
    else:
        print("\nAll integrations deployed and activated successfully!")
        sys.exit(0)