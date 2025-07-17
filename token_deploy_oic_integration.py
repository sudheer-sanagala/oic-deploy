import requests
import os
import json
import sys # For sys.exit()

def deploy_oic_integration(oic_url, bearer_token, iar_file_path):
    """
    Deploys a single Oracle Integration Cloud (.iar) file using a Bearer Token for authentication.

    Args:
        oic_url (str): The base URL of your OIC instance (e.g., https://your-instance.integration.ocp.oraclecloud.com).
                       It should not include the /ic/api/integration/v1 part, as the script adds it.
        bearer_token (str): The OAuth 2.0 Bearer Token for authentication.
        iar_file_path (str): The full path to the .iar file to deploy.

    Returns:
        bool: True if deployment and activation were successful, False otherwise.
    """

    # Construct the full base API URL
    base_api_url = oic_url
    if not base_api_url.endswith("/ic/api/integration/v1"):
        base_api_url = os.path.join(oic_url, "ic/api/integration/v1")

    import_url = f"{base_api_url}/integrations/archive?integrationInstance=oci-dev-oic01-axzg4y3f0m2n-px"
    activate_url_template = f"{base_api_url}/integrations/{{integration_id}}/activate"

    # Define common headers including the Authorization header with the Bearer Token
    common_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer_token}" # This is the key change!
    }

    print(f"\n--- Attempting deployment for: {os.path.basename(iar_file_path)} ---")

    try:
        # Check if the IAR file exists
        if not os.path.exists(iar_file_path):
            print(f"Error: The IAR file '{iar_file_path}' was not found. Skipping.")
            return False

        # 1. Upload/Import the .iar file
        print(f"  Step 1/2: Importing integration from '{os.path.basename(iar_file_path)}'...")
        with open(iar_file_path, 'rb') as iar_file:
            files = {'file': (os.path.basename(iar_file_path), iar_file, 'application/octet-stream')}
            
            # Use common_headers which includes the Bearer Token
            response = requests.post(import_url, files=files, headers=common_headers, verify=True)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

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
                "enableTracing": True # Set to False if you don't need tracing
            }
            
            # Headers for activation request, including Content-Type and Authorization
            activate_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {bearer_token}" # Use common_headers here too
            }

            # Make the POST request to activate the integration
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
        # Specific check for 401 Unauthorized, often due to invalid/expired token
        if e.response.status_code == 401:
            print("  Authentication failed! Please check your Bearer Token for validity and expiration.")
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
    # NEW: Bearer Token
    OIC_BEARER_TOKEN = os.environ.get("OIC_BEARER_TOKEN")
    IAR_FILES_INPUT = os.environ.get("IAR_FILES")

    # --- Validate Core Configuration ---
    if not OIC_URL:
        print("Error: OIC_URL environment variable is not set.")
        sys.exit(1)
    if not OIC_BEARER_TOKEN:
        print("Error: OIC_BEARER_TOKEN environment variable is not set. A valid Bearer Token is required.")
        sys.exit(1)
    if not IAR_FILES_INPUT:
        print("Error: IAR_FILES environment variable is not set. Please provide file paths or a directory.")
        sys.exit(1)

    # --- Determine files to deploy ---
    files_to_deploy = []
    if os.path.isdir(IAR_FILES_INPUT):
        print(f"IAR_FILES is a directory: '{IAR_FILES_INPUT}'. Searching for .iar files...")
        for root, _, files in os.walk(IAR_FILES_INPUT):
            for file in files:
                if file.endswith(".iar"):
                    files_to_deploy.append(os.path.join(root, file))
        if not files_to_deploy:
            print(f"No .iar files found in directory: '{IAR_FILES_INPUT}'.")
            sys.exit(1)
    else:
        # Assume it's a comma-separated list of files
        print(f"IAR_FILES is a list of files. Parsing: '{IAR_FILES_INPUT}'")
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
        # Pass the bearer_token instead of username/password
        success = deploy_oic_integration(OIC_URL, OIC_BEARER_TOKEN, iar_file)
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
        sys.exit(1) # Exit with a non-zero code to indicate overall failure
    else:
        print("\nAll integrations deployed and activated successfully!")
        sys.exit(0) # Exit with a zero code to indicate overall success