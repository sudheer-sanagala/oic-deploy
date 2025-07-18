import requests
import os
import json
import sys
import base64
# Removed: from dotenv import load_dotenv # Import load_dotenv to load environment variables into os.environ

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


def oic_project_import(oic_url, bearer_token, car_file_path, instance_name=None):
    """
    Imports a single Oracle OIC project archive (.car file) using a Bearer Token for authentication.
    Optionally targets a specific integration instance during import.
    This function *only* handles import, not replacement (PUT) as per the provided curl.
    """

    base_api_url = oic_url
    if not base_api_url.endswith("/ic/api/integration/v1"):
        base_api_url = os.path.join(oic_url, "ic/api/integration/v1")

    # Construct the import URL for POST /projects/archive
    target_import_url = f"{base_api_url}/projects/archive"
    if instance_name:
        target_import_url += f"?integrationInstance={instance_name}"
        print(f"  Import URL modified to target instance: {instance_name}")

    common_headers = {
        "Authorization": f"Bearer {bearer_token}"
    }

    print(f"\n--- Attempting project import for: {os.path.basename(car_file_path)} ---")

    response = None
    
    try:
        if not os.path.exists(car_file_path):
            print(f"Error: The .car file '{car_file_path}' was not found. Skipping.")
            return False

        # --- Attempt POST (Import) ---
        print(f"  Step 1/1: Attempting to POST (Import) project from '{os.path.basename(car_file_path)}'...")
        print(f"  Using POST Import URL: {target_import_url}")
        
        with open(car_file_path, 'rb') as car_file:
            files = {
                'file': (os.path.basename(car_file_path), car_file, 'application/octet-stream')
            }
            data = {
                'type': 'application/octet-stream' # As specified in the curl command
            }

            try:
                response = requests.post(target_import_url, files=files, data=data, headers=common_headers, verify=True, timeout=60)
                response.raise_for_status() # This will raise HTTPError for 4xx/5xx
                
                # OIC project import typically returns 200 OK with a JSON response or 204 No Content
                if response.status_code == 200:
                    import_result = response.json()
                    print(f"  POST Import API Response (JSON): {json.dumps(import_result, indent=2)}")
                    if import_result.get("status") == "SUCCESS": # Assuming a similar success status as integrations
                        print(f"  Successfully imported project via POST.")
                        return True
                    else:
                        error_message = import_result.get('message', 'Unknown error during POST import.')
                        print(f"  Error POSTing import project: {error_message}")
                        if response:
                            print(f"  Raw POST Import Response Text: {response.text}")
                        return False
                elif response.status_code == 204:
                    print(f"  POST Import for '{os.path.basename(car_file_path)}' returned 204 No Content (considered success).")
                    return True
                else:
                    print(f"  Unexpected status code for project import: {response.status_code}. Assuming failure.")
                    if response:
                        print(f"  Raw Project Import Response Text: {response.text}")
                    return False
            
            except requests.exceptions.HTTPError as e:
                print(f"  HTTP Error during POST import: {e}")
                if e.response is not None:
                    print(f"  Response Status Code: {e.response.status_code}")
                    print(f"  Response Content: {e.response.text}")
                if e.response.status_code == 401:
                    print("  Authentication failed! Please check your Bearer Token validity or OIC instance configuration.")
                return False
            except json.JSONDecodeError as e: # Catch JSON errors specifically for the POST response
                print(f"  Error: Failed to parse JSON response from OIC API (Import step). Details: {e}")
                print(f"  Raw OIC API Response Text (on JSONDecodeError):")
                print("  --- START RAW RESPONSE (OIC PROJECT IMPORT API) ---")
                if response:
                    print(response.text)
                else:
                    print("  No response object available.")
                print("  --- END RAW RESPONSE (OIC PROJECT IMPORT API) ---")
                print(f"  Project '{os.path.basename(car_file_path)}' import might have succeeded (Status 200), but response was not JSON.")
                return True

    except requests.exceptions.HTTPError as e:
        print(f"  HTTP Error during project import: {e}")
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
    except json.JSONDecodeError as e:
        print(f"  Error: Failed to parse JSON response from OIC API. Details: {e}")
        print(f"  Raw OIC API Response Text (on JSONDecodeError):")
        print("  --- START RAW RESPONSE (OIC API) ---")
        if response:
            print(response.text)
        else:
            print("  No response object available.")
        print("  --- END RAW RESPONSE (OIC API) ---")
        return False
    except Exception as e:
        print(f"  An unexpected error occurred: {e}")
        return False

if __name__ == "__main__":
    # --- Configuration ---
    # These variables must be set as environment variables in your operating system
    # or in your CI/CD pipeline (e.g., GitHub Actions Secrets).
    #
    # Example for setting locally (Linux/macOS):
    # export OIC_URL="https://your-oic-instance.oraclecloud.com"
    # export CAR_FILES="project1.car,project2.car"
    # export OIC_TOKEN_URL="https://idcs-xxxxxxxx.identity.oraclecloud.com/oauth2/v1/token"
    # export OIC_CLIENT_ID="your_client_id"
    # export OIC_CLIENT_SECRET="your_client_secret"
    # export OIC_SCOPE="https://your_oic_instance_url:443urn:opc:resource:consumer::all"
    # export OIC_INSTANCE_NAME="service-instance" # Optional
    # export OIC_FALLBACK_BEARER_TOKEN="your_pre_generated_token" # Optional

    OIC_URL = os.environ.get("OIC_URL")
    CAR_FILES_INPUT = os.environ.get("CAR_FILES")

    # OAuth Client Credentials for Token Fetching
    OIC_TOKEN_URL = os.environ.get("OIC_TOKEN_URL")
    OIC_CLIENT_ID = os.environ.get("OIC_CLIENT_ID")
    OIC_CLIENT_SECRET = os.environ.get("OIC_CLIENT_SECRET")
    OIC_SCOPE = os.environ.get("OIC_SCOPE")

    # Optional Integration Instance Name (used in import URLs)
    OIC_INSTANCE_NAME = os.environ.get("OIC_INSTANCE_NAME")

    # Fallback Bearer Token (for when automatic fetching fails or credentials are not provided)
    OIC_FALLBACK_BEARER_TOKEN = os.environ.get("OIC_FALLBACK_BEARER_TOKEN")


    # --- Validate Core Configuration ---
    if not OIC_URL:
        print("Error: OIC_URL environment variable is not set.")
        sys.exit(1)
    if not CAR_FILES_INPUT:
        print("Error: CAR_FILES environment variable is not set. Please provide file paths or a directory.")
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
    if os.path.isdir(CAR_FILES_INPUT):
        print(f"\nCAR_FILES is a directory: '{CAR_FILES_INPUT}'. Searching for .car files...")
        for root, _, files in os.walk(CAR_FILES_INPUT):
            for file in files:
                if file.endswith(".car"):
                    files_to_deploy.append(os.path.join(root, file))
        if not files_to_deploy:
            print(f"No .car files found in directory: '{CAR_FILES_INPUT}'.")
            sys.exit(1)
    else:
        print(f"\nCAR_FILES is a list of files. Parsing: '{CAR_FILES_INPUT}'")
        files_to_deploy = [f.strip() for f in CAR_FILES_INPUT.split(',') if f.strip()]
        if not files_to_deploy:
            print("No valid .car file paths found in CAR_FILES environment variable.")
            sys.exit(1)

    print(f"\nFound {len(files_to_deploy)} .car file(s) for deployment:")
    for f in files_to_deploy:
        print(f"  - {f}")

    # --- Execute Deployment for each file ---
    overall_success = True
    deployment_results = {}

    for car_file in files_to_deploy:
        file_basename = os.path.basename(car_file)
        success = oic_project_import(OIC_URL, bearer_token, car_file, OIC_INSTANCE_NAME)
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
        print("\nOne or more projects failed to import. Please review the logs above for details.")
        sys.exit(1)
    else:
        print("\nAll projects imported successfully!")
        sys.exit(0)
