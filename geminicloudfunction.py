import functions_framework
import requests
import os
import base64
import vertexai
import json
import requests
import base64
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from vertexai.generative_models import GenerationConfig, GenerativeModel, Part
import vertexai.preview.generative_models as generative_models
import re




# Headers without authentication (no GitHub token required)
headers = {
    'Accept': 'application/vnd.github.v3+json'
}

def list_files_in_repo(owner, repo, path=""):
    """
    Recursively list all files in the GitHub repository.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Error accessing {path}: {response.status_code}")
        return []

    items = response.json()
    file_paths = []

    for item in items:
        if item['type'] == 'file':
            file_paths.append(item['path'])
        elif item['type'] == 'dir':
            # Recursively get files from directories
            file_paths.extend(list_files_in_repo(owner, repo, item['path']))
    
    return file_paths

def download_file(owner, repo, file_path):
    """
    Download the content of a file from the GitHub repository and decode it.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to download {file_path}: {response.status_code}")
        return None

    file_content = response.json()
    if 'content' in file_content:
        # Decode the Base64 content to plain text
        decoded_content = base64.b64decode(file_content['content']).decode('utf-8')
        return decoded_content
    else:
        print(f"No content found for {file_path}")
        return None

def save_code_files(owner, repo):
    """
    Retrieve all code files from the repository and save their content.
    """
    all_files = list_files_in_repo(owner, repo)
    code_files_content = []

    for file in all_files:
        content = download_file(owner, repo, file)
        if content:
            code_files_content.append({"file_path": file, "content": content})

    return code_files_content


system_instruction = '''You are an expert in code analysis. Your role is to carefully review any provided code, analyze it for correctness, efficiency, security, and best practices, and respond only based on the code data that has been attached to the query.

For every query, you must provide a response with the following structure:

RESPONSE: This should contain a detailed answer or explanation about the code, addressing any specific questions from the user, including improvements, potential issues, or verification of correctness.
STATUS: This should be either APPROVE or REJECT.
APPROVE: If the code is free from issues, security vulnerabilities, inefficiencies, or violations of best practices.
REJECT: If there are any issues such as bugs, security risks, inefficiencies, or poor adherence to best practices. Clearly state the reason(s) for rejection in the response.
You are not allowed to infer anything beyond the attached code. If the context is insufficient or no code is provided, politely state that the necessary code context is missing.

Ensure that your analysis is precise and concise. You are expected to:

Identify bugs or inefficiencies.
Recommend improvements where applicable.
Ensure that the code follows security and performance best practices.
All responses should strictly adhere to this format:
{
  "RESPONSE": "Your detailed analysis or answer here...",
  "STATUS": "APPROVE" or "REJECT"
}'''

safety_settings = {
    generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH:generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT:generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
    generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_ONLY_HIGH,
}

# Define the Cloud Function
@functions_framework.http
def query_gemini(request):
    request_json = request.get_json(silent=True)
    print(request_json)
    request_args = request.args
    query = request_json['query']
    # GitHub configuration
    REPO_OWNER = request_json['REPO_OWNER']     # Replace with the owner of the repository
    REPO_NAME = request_json['REPO_NAME']      # Replace with the name of the repository
    # GitHub code scanning
    print("Scanning GitHub repository...")
    code_files = save_code_files(REPO_OWNER, REPO_NAME)
    code_to_analyze = "\n".join([f"File: {code_file['file_path']}\nContent:\n{code_file['content']}" for code_file in code_files])
    



     # TODO(developer): Update project_id and location
    vertexai.init(project="ankercloud-testing-account", location="us-central1")

    model = GenerativeModel(model_name="gemini-1.5-flash-002",system_instruction=system_instruction,safety_settings=safety_settings)

    # Generation Config
    config = GenerationConfig(
        max_output_tokens=2048, temperature=0.4, top_p=1, top_k=32
    )

    # Generate text
    response = model.generate_content(
        [query,code_to_analyze], generation_config=config
    )
    print('FULL RESPONSE',response)
    OUTPUT = response.text
    print('TEXT RESPONSE',OUTPUT)

    STATUS = None
    MODEL_RESPONSE =None
    # Regex pattern to extract the STATUS value
    status_pattern = r'"STATUS":\s*"([^"]+)"'
    query_pattern = r'"RESPONSE":\s*"([^"]+)"'
    # Search for the pattern in the string
    status_match = re.search(status_pattern, OUTPUT)
    response_match = re.search(query_pattern, OUTPUT)
    # Check if STATUS was found and print the result
    if status_match:
        STATUS = status_match.group(1)  # Extract the matched status value
        print(f"Extracted Status: {STATUS}")
    else:
        print("STATUS not available")

    # Check if STATUS was found and print the result
    if response_match:
        MODEL_RESPONSE = response_match.group(1)  # Extract the matched status value
        print(f"Extracted Response: {MODEL_RESPONSE}")
    else:
        print("Response not available")

    # Replace these variables with your own values
    GITHUB_TOKEN = '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'  # Preferably, read from an environment variable
    WORKFLOW_ID = 'main.yml'  # Filename of your workflow or its ID
    REF = 'main'  # The branch to run the workflow on

    # Optional: Inputs for the workflow (if defined)
    WORKFLOW_INPUTS = {
    # 'input_name': 'value',
    }

    # GitHub API endpoint
    url = f'https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{WORKFLOW_ID}/dispatches'

    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': f'Bearer {GITHUB_TOKEN}',
    }

    data = {
        'ref': REF,
    # 'inputs': WORKFLOW_INPUTS,
    }

    if STATUS=='APPROVE':
        response = requests.post(url, headers=headers, data=json.dumps(data))

        if response.status_code == 204:
            print('Workflow dispatched successfully.')
        else:
            print(f'Failed to dispatch workflow: {response.status_code}')
            print(response.text)
    else:
        print('Status Rejected. No action required!')

    
    return json.dumps({'response': MODEL_RESPONSE,'status':STATUS}), 200, {'Content-Type': 'application/json'}

