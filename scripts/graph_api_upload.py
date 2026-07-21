#!/usr/bin/env python3
"""
SharePoint File Upload via Microsoft Graph API

This script provides a working alternative to the broken Relevance AI
SharePoint__Upload_File MCP tool. It uploads files to SharePoint/Teams
using direct Graph API calls.

Usage:
    from graph_api_upload import upload_file_to_sharepoint

    result = upload_file_to_sharepoint(
        drive_id="b!abc...",
        folder_path="/Documents",
        file_name="transcript.pdf",
        file_url="https://example.com/file.pdf",
        oauth_token="eyJ..."
    )

    print(result['web_url'])  # Access the uploaded file
"""

import requests
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_folder_id(
    drive_id: str,
    folder_path: str,
    oauth_token: str
) -> str:
    """
    Resolve a folder path to its SharePoint item ID.

    Args:
        drive_id: The SharePoint/Teams drive ID
        folder_path: Path within the drive (e.g., "/Documents" or "")
        oauth_token: Microsoft 365 OAuth access token

    Returns:
        str: The folder's SharePoint item ID, or 'root' for the drive root

    Raises:
        requests.HTTPError: If the Graph API call fails
    """
    if not folder_path or folder_path == "/":
        return "root"

    # Normalize the path
    folder_path = folder_path.strip("/")

    # Query Graph API to resolve the path to an item ID
    # Using the path-based addressing: /drives/{drive-id}/root:/{path}
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}"

    headers = {
        "Authorization": f"Bearer {oauth_token}",
        "Accept": "application/json",
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    data = response.json()
    return data.get("id", "root")


def download_file(file_url: str) -> bytes:
    """
    Download a file from a URL.

    Args:
        file_url: URL to download from

    Returns:
        bytes: File content

    Raises:
        requests.HTTPError: If the download fails
    """
    response = requests.get(file_url, timeout=60)
    response.raise_for_status()
    return response.content


def upload_file_to_sharepoint(
    drive_id: str,
    folder_path: str,
    file_name: str,
    file_url: str,
    oauth_token: str,
    timeout: int = 120
) -> Dict[str, Any]:
    """
    Upload a file to SharePoint using Microsoft Graph API.

    This is a complete replacement for the broken Relevance AI
    SharePoint__Upload_File tool.

    Args:
        drive_id: The SharePoint/Teams drive ID
        folder_path: Target folder path (e.g., "/Documents" or "")
        file_name: Name to save the file as (e.g., "transcript.pdf")
        file_url: URL to download the file from
        oauth_token: Microsoft 365 OAuth access token with
                     Files.ReadWrite.All and Sites.ReadWrite.All permissions
        timeout: Request timeout in seconds (default 120)

    Returns:
        dict: Upload result with keys:
            - success (bool): Whether the upload succeeded
            - web_url (str): Public URL to access the file
            - item_id (str): SharePoint item ID
            - file_name (str): Name saved as
            - drive_id (str): Drive ID
            - size (int): File size in bytes
            - error (str|None): Error message if failed

    Raises:
        requests.HTTPError: If any Graph API call fails
        Exception: For other errors (download failure, etc.)
    """
    try:
        logger.info(f"Uploading {file_name} to SharePoint drive {drive_id}")

        # Step 1: Resolve the folder path to an item ID
        logger.debug(f"Resolving folder path: {folder_path}")
        folder_id = resolve_folder_id(drive_id, folder_path, oauth_token)
        logger.debug(f"Resolved folder ID: {folder_id}")

        # Step 2: Download the file
        logger.debug(f"Downloading file from {file_url}")
        file_bytes = download_file(file_url)
        file_size = len(file_bytes)
        logger.debug(f"Downloaded {file_size} bytes")

        # Step 3: Upload to SharePoint using the simple upload API
        # This endpoint automatically creates the file if it doesn't exist
        upload_url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/"
            f"items/{folder_id}:/{file_name}:/content"
        )

        headers = {
            "Authorization": f"Bearer {oauth_token}",
            "Content-Type": "application/octet-stream",
        }

        logger.info(f"Uploading to {upload_url}")
        response = requests.put(
            upload_url,
            data=file_bytes,
            headers=headers,
            timeout=timeout
        )
        response.raise_for_status()

        upload_response = response.json()

        # Step 4: Extract the important metadata
        web_url = upload_response.get("webUrl", "")
        item_id = upload_response.get("id", "")

        result = {
            "success": True,
            "web_url": web_url,
            "item_id": item_id,
            "file_name": upload_response.get("name", file_name),
            "drive_id": drive_id,
            "folder_id": folder_id,
            "size": upload_response.get("size", file_size),
            "error": None,
        }

        logger.info(f"Upload successful: {web_url}")
        return result

    except requests.HTTPError as e:
        logger.error(f"Graph API error: {e.response.status_code} {e.response.text}")
        return {
            "success": False,
            "web_url": None,
            "item_id": None,
            "file_name": file_name,
            "drive_id": drive_id,
            "folder_id": None,
            "size": 0,
            "error": f"Graph API error: {e}",
        }
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return {
            "success": False,
            "web_url": None,
            "item_id": None,
            "file_name": file_name,
            "drive_id": drive_id,
            "folder_id": None,
            "size": 0,
            "error": str(e),
        }


def upload_file_from_disk(
    drive_id: str,
    folder_path: str,
    file_path: str,
    oauth_token: str,
) -> Dict[str, Any]:
    """
    Upload a file from disk to SharePoint.

    Args:
        drive_id: The SharePoint/Teams drive ID
        folder_path: Target folder path
        file_path: Local path to the file to upload
        oauth_token: Microsoft 365 OAuth access token

    Returns:
        dict: Upload result (same as upload_file_to_sharepoint)
    """
    path = Path(file_path)
    file_name = path.name
    file_bytes = path.read_bytes()

    # Build a simple HTTP server URL for the file
    # In practice, you'd upload from disk directly or use a local URL
    # This is a simplified example - for production, implement proper
    # local file serving or use the direct bytes approach below

    # More direct approach: upload the bytes directly
    try:
        folder_id = resolve_folder_id(drive_id, folder_path, oauth_token)

        upload_url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/"
            f"items/{folder_id}:/{file_name}:/content"
        )

        headers = {
            "Authorization": f"Bearer {oauth_token}",
            "Content-Type": "application/octet-stream",
        }

        response = requests.put(
            upload_url,
            data=file_bytes,
            headers=headers,
            timeout=120
        )
        response.raise_for_status()

        upload_response = response.json()

        return {
            "success": True,
            "web_url": upload_response.get("webUrl", ""),
            "item_id": upload_response.get("id", ""),
            "file_name": upload_response.get("name", file_name),
            "drive_id": drive_id,
            "folder_id": folder_id,
            "size": upload_response.get("size", file_bytes.__sizeof__()),
            "error": None,
        }
    except Exception as e:
        logger.error(f"Upload from disk failed: {e}")
        return {
            "success": False,
            "web_url": None,
            "item_id": None,
            "file_name": file_name,
            "drive_id": drive_id,
            "folder_id": None,
            "size": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    # Example usage (requires valid OAuth token)
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 5:
        print(
            "Usage: python graph_api_upload.py "
            "<drive_id> <folder_path> <file_name> <file_url> [token_file]"
        )
        print()
        print("Example:")
        print(
            '  python graph_api_upload.py "b!abc..." "/Documents" '
            '"transcript.pdf" "https://example.com/file.pdf" token.txt'
        )
        sys.exit(1)

    drive_id = sys.argv[1]
    folder_path = sys.argv[2]
    file_name = sys.argv[3]
    file_url = sys.argv[4]
    token_file = sys.argv[5] if len(sys.argv) > 5 else None

    # Load token from file if provided
    if token_file:
        with open(token_file) as f:
            oauth_token = f.read().strip()
    else:
        print("Error: OAuth token required (pass as file path)")
        sys.exit(1)

    result = upload_file_to_sharepoint(
        drive_id=drive_id,
        folder_path=folder_path,
        file_name=file_name,
        file_url=file_url,
        oauth_token=oauth_token,
    )

    if result["success"]:
        print(f"✓ Upload successful!")
        print(f"  Web URL: {result['web_url']}")
        print(f"  Item ID: {result['item_id']}")
        print(f"  Size: {result['size']} bytes")
    else:
        print(f"✗ Upload failed: {result['error']}")
        sys.exit(1)
