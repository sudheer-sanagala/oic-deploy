import requests
import os
import json
import sys
import base64

def get_bearer_token(token_url, client_id, client_secret, scope):
    """
    Fetches an OAuth 2.0 Bearer Token using the Client Credentials Grant type.

    Args:
        token_url (str): The URL of the OAuth token endpoint (e.g., IDCS/OCI IAM).
        client_id (str): The Client ID of your confidential application.
        client_secret (str): The Client Secret of your confidential application.
        scope (str): The scope required for the token, specific to your OIC instance.

    Returns:
        str: The fetched Bearer Token, or None if an error occurs.
    """
    print("\n--- Attempting to fetch Bearer Token ---")
    
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

    payload = f'grant_type=client_credentials&scope={scope}'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {encoded_credentials}'
    }

    try:
        response = requests.post(token_url, headers=headers, data=payload, verify=True)
        response.raise_for_status()

        token_response = response.json()
        print(f"Token API Response: {json.dumps(token_response, indent=2)}")

        bearer_token = token_response.get("access_token")
        if bearer_token:
            print("Successfully fetched Bearer Token.")
            return bearer_token
        else:
            print("Error: 'access_token' not found in the token response.")
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
        return None
    except json.JSONDecodeError:
        print(f"Error: Failed to parse JSON response from token endpoint. Raw response: {response.text}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while fetching token: {e}")
        return None

def deploy_oic_integration(oic_url, bearer_token, iar_file_path, instance_name=None):
    """
    Deploys a single Oracle Integration Cloud (.iar) file using a Bearer Token for authentication.
    Optionally targets a specific integration instance during import.

    Args:
        oic_url (str): The base URL of your OIC instance.
        bearer_token (str): The OAuth 2.0 Bearer Token for authentication.
        iar_file_path (str): The full path to the .iar file to deploy.
        instance_name (str, optional): The name of the integration instance to target.
                                       If provided, '?integrationInstance={instance_name}'
                                       will be appended to the import URL. Defaults to None.

    Returns:
        bool: True if deployment and activation were successful, False otherwise.
    """

    # Construct the full base API URL
    base_api_url = oic_url
    if not base_api_url.endswith("/ic/api/integration/v1"):
        base_api_url = os.path.join(oic_url, "ic/api/integration/v1")

    # Construct the import URL, conditionally adding instance_name
    import_url = f"{base_api_url}/integrations/archive"
    if instance_name:
        import_url += f"?integrationInstance={instance_name}"
        print(f"  Import URL modified to target instance: {instance_name}")


    activate_url_template = f"{base_api_url}/integrations/{{integration_id}}/activate"

    # Define common headers including the Authorization header with the Bearer Token
    common_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}"
    }

    print(f"\n--- Attempting deployment for: {os.path.basename(iar_file_path)} ---")

    try:
        # Check if the IAR file exists
        if not os.path.exists(iar_file_path):
            print(f"Error: The IAR file '{iar_file_path}' was not found. Skipping.")
            return False

        # 1. Upload/Import the .iar file
        print(f"  Step 1/2: Importing integration from '{os.path.basename(iar_file_path)}'...")
        print(f"  Using Import URL: {import_url}") # Log the full import URL
        with open(iar_file_path, 'rb') as iar_file:
            files = {'file': (os.path.basename(iar_file_path), iar_file, 'application/octet-stream')}
            
            response = requests.post(import_url, files=files, headers=common_headers, verify=True)
            print(f"response - {response.text}")
            response.raise_for_status()

        import_result = response.json()
        print(f"  Import API Response: {json.dumps(import_result, indent=2)}")

        if import_result.get("status") == "SUCCESS":
            integration_id = import_result.get("id")
            if not integration_id:
                print("  Error: Could not retrieve integration ID from import response. Import might have failed silently.")
                return False

            print(f"  Successfully imported integration with ID: '{integration_id}'.")

            # 2. Activate the integration
            activate_url = activate_url_template.format(integration_id=integration_id)
            print(f"  Step 2/2: Activating integration '{integration_id}'...")

            activate_payload = {
                "enableTracing": False
            }
            
            activate_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {bearer_token}"
            }

            response = requests.post(activate_url, headers=activate_headers, json=activate_payload, verify=True)
            response.raise_for_status()

            activate_result = response.json()
            print(f"  Activation API Response: {json.dumps(activate_result, indent=2)}")

            if activate_result.get("status") == "SUCCESS":
                print(f"  Integration '{integration_id}' activated successfully!")
                return True
            else:
                error_message = activate_result.get('message', 'Unknown error during activation.')
                print(f"  Error activating integration '{integration_id}': {error_message}")
                return False
        else:
            error_message = import_result.get('message', 'Unknown error during import.')
            print(f"  Error importing integration: {error_message}")
            return False

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
        return False
    except json.JSONDecodeError:
        print(f"  Error: Failed to parse JSON response from OIC API. Raw response: {response.text}")
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

    # NEW: Optional Integration Instance Name
    # If provided, this will be appended to the import URL as ?integrationInstance={instance_name}
    OIC_INSTANCE_NAME = os.environ.get("OIC_INSTANCE_NAME")

    # --- Validate Core Configuration ---
    if not OIC_URL:
        print("Error: OIC_URL environment variable is not set.")
        sys.exit(1)
    if not IAR_FILES_INPUT:
        print("Error: IAR_FILES environment variable is not set. Please provide file paths or a directory.")
        sys.exit(1)
    if not OIC_TOKEN_URL:
        print("Error: OIC_TOKEN_URL environment variable is not set.")
        sys.exit(1)
    if not OIC_CLIENT_ID:
        print("Error: OIC_CLIENT_ID environment variable is not set.")
        sys.exit(1)
    if not OIC_CLIENT_SECRET:
        print("Error: OIC_CLIENT_SECRET environment variable is not set.")
        sys.exit(1)
    if not OIC_SCOPE:
        print("Error: OIC_SCOPE environment variable is not set.")
        sys.exit(1)
    # OIC_INSTANCE_NAME is optional, so no validation here.

    # --- Fetch Bearer Token ---
    bearer_token = get_bearer_token(OIC_TOKEN_URL, OIC_CLIENT_ID, OIC_CLIENT_SECRET, OIC_SCOPE)
    if not bearer_token:
        print("\nFailed to obtain Bearer Token. Exiting deployment.")
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
    deployment_results = {} # To store results for summary

    for iar_file in files_to_deploy:
        file_basename = os.path.basename(iar_file)
        # Pass the fetched bearer_token AND the optional OIC_INSTANCE_NAME
        success = deploy_oic_integration(OIC_URL, bearer_token, iar_file, OIC_INSTANCE_NAME)
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