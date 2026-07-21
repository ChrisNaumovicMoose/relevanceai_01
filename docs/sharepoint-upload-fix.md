# SharePoint Upload Tool Fix

## Problem

The Relevance AI `SharePoint__Upload_File` MCP tool (from the Microsoft 365 integration) has a critical bug:

```
NameError: name 'upload_url' is not defined
  Line 3, in <module>
    if isinstance(upload_url, dict):
```

The tool's internal code references a variable that was never assigned, causing it to fail before even attempting to contact SharePoint. This breaks any workflow that tries to upload files to SharePoint/Teams.

## Workaround

Until the MCP tool is fixed by Relevance AI, use one of these alternatives:

### Option 1: Use Permanent Export URLs (Quick Fix)
If you're uploading exported data (like transcripts), use the permanent URL from `Export_data_to_permanent_downloadable_file` directly instead of uploading to SharePoint:

```python
# Instead of:
# sharepoint_upload_file(drive_id=..., file_url=..., ...)

# Use the permanent URL directly:
permanent_url = export_response['permanent_url']
# Include this URL in your summary/transcript
```

**Pros:** No SharePoint upload needed, URL is permanent and accessible
**Cons:** Files live on Relevance's servers, not in your Teams/SharePoint

### Option 2: Custom Wrapper Tool (In Progress)
A custom Relevance tool (`SharePoint_Upload_File_Fixed`) is being developed in the workspace to implement SharePoint uploads using direct Graph API calls, bypassing the broken MCP tool.

**Status:** Draft — requires OAuth token integration
**Pros:** Full SharePoint integration, files in Teams/SharePoint
**Cons:** Requires Graph API configuration

### Option 3: Direct Graph API Integration
For advanced use cases, implement SharePoint uploads directly using Microsoft Graph API:

```python
import requests
import json

def upload_to_sharepoint(drive_id, folder_id, file_name, file_bytes, oauth_token):
    """
    Upload a file to SharePoint using Microsoft Graph API.
    
    Args:
        drive_id: SharePoint/Teams drive ID
        folder_id: Target folder item ID (or 'root')
        file_name: Name to save as
        file_bytes: File content
        oauth_token: Microsoft 365 OAuth access token
    
    Returns:
        dict: Upload response with webUrl and driveItem metadata
    """
    url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}:/{file_name}:/content'
    
    headers = {
        'Authorization': f'Bearer {oauth_token}',
        'Content-Type': 'application/octet-stream',
    }
    
    response = requests.put(url, data=file_bytes, headers=headers)
    response.raise_for_status()
    
    return response.json()
```

See [`/scripts/graph_api_upload.py`](../scripts/graph_api_upload.py) for a complete implementation.

## Reporting the Bug

This bug should be reported to Relevance AI support:

**Bug Details:**
- **Tool:** SharePoint__Upload_File (Microsoft 365 MCP server)
- **Error:** NameError: name 'upload_url' is not defined at line 3
- **Impact:** Blocks all SharePoint file uploads via Relevance workflows
- **Workaround:** Use permanent export URLs or direct Graph API calls

Contact Relevance AI support with these details to request a fix.

## References

- Microsoft Graph Drive Upload API: https://learn.microsoft.com/en-us/graph/api/driveitem-put-content
- Relevance AI SharePoint Tools: Check workspace for `SharePoint_Upload_File_Fixed` (draft)
- Teams Migration Script: See [`/scripts/teams_migration/migrate_channel.py`](../scripts/teams_migration/migrate_channel.py) for Graph API patterns used in this codebase
