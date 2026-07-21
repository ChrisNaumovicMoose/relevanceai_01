#!/usr/bin/env python3
"""
Test suite for graph_api_upload.py

Tests the SharePoint upload implementation without requiring real
SharePoint credentials or Graph API access.

Run with:
    python -m pytest test_graph_api_upload.py -v

Or without pytest:
    python test_graph_api_upload.py
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import sys
from pathlib import Path

# Add parent directory to path so we can import graph_api_upload
sys.path.insert(0, str(Path(__file__).parent))

from graph_api_upload import (
    resolve_folder_id,
    download_file,
    upload_file_to_sharepoint,
)


class TestResolveFolderId(unittest.TestCase):
    """Tests for folder path resolution."""

    def test_resolve_folder_id_root(self):
        """Empty path should return 'root'."""
        result = resolve_folder_id("drive123", "", "token")
        self.assertEqual(result, "root")

    def test_resolve_folder_id_slash(self):
        """Path '/' should return 'root'."""
        result = resolve_folder_id("drive123", "/", "token")
        self.assertEqual(result, "root")

    @patch("graph_api_upload.requests.get")
    def test_resolve_folder_id_with_path(self, mock_get):
        """Should resolve nested folder path to item ID."""
        # Mock the Graph API response
        mock_response = Mock()
        mock_response.json.return_value = {"id": "item123abc"}
        mock_get.return_value = mock_response

        result = resolve_folder_id("drive123", "/Documents/Reports", "token")

        # Verify the correct Graph API endpoint was called
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        self.assertIn("drive123", call_url)
        self.assertIn("/Documents/Reports", call_url)

        # Verify the authorization header
        headers = mock_get.call_args[1]["headers"]
        self.assertIn("Bearer token", headers["Authorization"])

        self.assertEqual(result, "item123abc")

    @patch("graph_api_upload.requests.get")
    def test_resolve_folder_id_api_error(self, mock_get):
        """Should raise error if Graph API fails."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response

        with self.assertRaises(Exception):
            resolve_folder_id("drive123", "/NonExistent", "token")


class TestDownloadFile(unittest.TestCase):
    """Tests for file download."""

    @patch("graph_api_upload.requests.get")
    def test_download_file_success(self, mock_get):
        """Should download file content successfully."""
        file_content = b"PDF content here" * 100
        mock_response = Mock()
        mock_response.content = file_content
        mock_get.return_value = mock_response

        result = download_file("https://example.com/file.pdf")

        # Verify correct URL was requested
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args[0][0], "https://example.com/file.pdf")

        # Verify content returned
        self.assertEqual(result, file_content)
        self.assertEqual(len(result), len(file_content))

    @patch("graph_api_upload.requests.get")
    def test_download_file_large(self, mock_get):
        """Should handle large files."""
        file_content = b"x" * (10 * 1024 * 1024)  # 10 MB
        mock_response = Mock()
        mock_response.content = file_content
        mock_get.return_value = mock_response

        result = download_file("https://example.com/large.bin")

        self.assertEqual(len(result), 10 * 1024 * 1024)

    @patch("graph_api_upload.requests.get")
    def test_download_file_error(self, mock_get):
        """Should raise error on download failure."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("Connection timeout")
        mock_get.return_value = mock_response

        with self.assertRaises(Exception):
            download_file("https://example.com/missing.pdf")


class TestUploadFileToSharePoint(unittest.TestCase):
    """Tests for complete upload workflow."""

    @patch("graph_api_upload.resolve_folder_id")
    @patch("graph_api_upload.download_file")
    @patch("graph_api_upload.requests.put")
    def test_upload_success(self, mock_put, mock_download, mock_resolve):
        """Should successfully upload file and return metadata."""
        # Setup mocks
        mock_resolve.return_value = "folder123"
        mock_download.return_value = b"PDF content" * 100

        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "item456",
            "name": "transcript.pdf",
            "webUrl": "https://company.sharepoint.com/sites/team/Documents/transcript.pdf",
            "size": 1100,
        }
        mock_put.return_value = mock_response

        # Execute upload
        result = upload_file_to_sharepoint(
            drive_id="drive123",
            folder_path="/Documents",
            file_name="transcript.pdf",
            file_url="https://example.com/transcript.pdf",
            oauth_token="token_abc123",
        )

        # Verify success
        self.assertTrue(result["success"])
        self.assertEqual(result["item_id"], "item456")
        self.assertEqual(result["file_name"], "transcript.pdf")
        self.assertIn("sharepoint.com", result["web_url"])
        self.assertIsNone(result["error"])

        # Verify Graph API was called correctly
        mock_put.assert_called_once()
        put_url = mock_put.call_args[0][0]
        self.assertIn("drive123", put_url)
        self.assertIn("transcript.pdf", put_url)

        # Verify authorization header
        headers = mock_put.call_args[1]["headers"]
        self.assertIn("Bearer token_abc123", headers["Authorization"])
        self.assertEqual(headers["Content-Type"], "application/octet-stream")

    @patch("graph_api_upload.resolve_folder_id")
    @patch("graph_api_upload.download_file")
    @patch("graph_api_upload.requests.put")
    def test_upload_to_root(self, mock_put, mock_download, mock_resolve):
        """Should upload to root folder when no path specified."""
        mock_resolve.return_value = "root"
        mock_download.return_value = b"content"
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "item789",
            "webUrl": "https://example.com/file.txt",
            "size": 7,
        }
        mock_put.return_value = mock_response

        result = upload_file_to_sharepoint(
            drive_id="drive123",
            folder_path="",
            file_name="file.txt",
            file_url="https://example.com/file.txt",
            oauth_token="token",
        )

        self.assertTrue(result["success"])
        # Verify folder_id is set to 'root'
        mock_resolve.assert_called_once_with("drive123", "", "token")

    @patch("graph_api_upload.resolve_folder_id")
    @patch("graph_api_upload.download_file")
    @patch("graph_api_upload.requests.put")
    def test_upload_network_error(self, mock_put, mock_download, mock_resolve):
        """Should handle network errors gracefully."""
        mock_resolve.return_value = "folder123"
        mock_download.return_value = b"content"
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("Network error")
        mock_put.return_value = mock_response

        result = upload_file_to_sharepoint(
            drive_id="drive123",
            folder_path="/Documents",
            file_name="file.txt",
            file_url="https://example.com/file.txt",
            oauth_token="token",
        )

        # Should return failure with error message
        self.assertFalse(result["success"])
        self.assertIsNotNone(result["error"])
        self.assertIn("error", result["error"].lower())

    @patch("graph_api_upload.resolve_folder_id")
    @patch("graph_api_upload.download_file")
    def test_upload_download_error(self, mock_download, mock_resolve):
        """Should handle download failure."""
        mock_resolve.return_value = "folder123"
        mock_download.side_effect = Exception("Download failed")

        result = upload_file_to_sharepoint(
            drive_id="drive123",
            folder_path="/Documents",
            file_name="file.txt",
            file_url="https://example.com/file.txt",
            oauth_token="token",
        )

        self.assertFalse(result["success"])
        self.assertIsNotNone(result["error"])

    @patch("graph_api_upload.resolve_folder_id")
    @patch("graph_api_upload.download_file")
    @patch("graph_api_upload.requests.put")
    def test_upload_with_special_characters(self, mock_put, mock_download, mock_resolve):
        """Should handle file names with special characters."""
        mock_resolve.return_value = "folder123"
        mock_download.return_value = b"content"
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "item999",
            "webUrl": "https://example.com/file.txt",
            "name": "Report - 2024-01-15.pdf",
        }
        mock_put.return_value = mock_response

        result = upload_file_to_sharepoint(
            drive_id="drive123",
            folder_path="/Documents",
            file_name="Report - 2024-01-15.pdf",
            file_url="https://example.com/report.pdf",
            oauth_token="token",
        )

        self.assertTrue(result["success"])
        self.assertIn("2024-01-15", result["file_name"])


class TestIntegration(unittest.TestCase):
    """Integration tests simulating real workflows."""

    @patch("graph_api_upload.requests.get")
    @patch("graph_api_upload.requests.put")
    def test_full_upload_workflow(self, mock_put, mock_get):
        """Simulate a complete upload workflow."""
        # Setup mocks

        # First call: resolve folder
        resolve_response = Mock()
        resolve_response.json.return_value = {"id": "folder_uuid"}

        # Second call: download file
        download_response = Mock()
        download_response.content = b"Test PDF content"

        # Third call: upload file
        upload_response = Mock()
        upload_response.json.return_value = {
            "id": "uploaded_item_uuid",
            "name": "test_transcript.pdf",
            "webUrl": "https://company.sharepoint.com/sites/sales/Documents/test_transcript.pdf",
            "size": 15,
        }

        # Configure mock to return different responses for different calls
        mock_get.side_effect = [resolve_response, download_response]
        mock_put.return_value = upload_response

        # Execute full workflow
        result = upload_file_to_sharepoint(
            drive_id="b!12345abcde",
            folder_path="/Shared Documents",
            file_name="test_transcript.pdf",
            file_url="https://permanent.storage.example.com/exports/12345.pdf",
            oauth_token="eyJ0eXAiOiJKV1QiLCJhbGc...",
        )

        # Verify success
        self.assertTrue(result["success"])
        self.assertEqual(result["file_name"], "test_transcript.pdf")
        self.assertIn("sharepoint.com", result["web_url"])
        self.assertEqual(result["size"], 15)
        self.assertIsNone(result["error"])

        # Verify all API calls were made
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(mock_put.call_count, 1)

    @patch("graph_api_upload.requests.get")
    @patch("graph_api_upload.requests.put")
    def test_upload_multiple_files(self, mock_put, mock_get):
        """Simulate uploading multiple files to same folder."""
        # Setup mocks
        resolve_response = Mock()
        resolve_response.json.return_value = {"id": "folder_id"}

        download_response = Mock()
        download_response.content = b"content"

        upload_response = Mock()
        upload_response.json.return_value = {
            "id": "item_id",
            "webUrl": "https://example.com/file",
            "name": "file.pdf",
            "size": 7,
        }

        mock_get.side_effect = [resolve_response, download_response, resolve_response, download_response]
        mock_put.side_effect = [upload_response, upload_response]

        results = []

        # Upload two files
        for i, filename in enumerate(["transcript_1.pdf", "transcript_2.pdf"]):
            result = upload_file_to_sharepoint(
                drive_id="drive_id",
                folder_path="/Documents",
                file_name=filename,
                file_url="https://example.com/file.pdf",
                oauth_token="token",
            )
            results.append(result)

        # Both should succeed
        for result in results:
            self.assertTrue(result["success"])
            self.assertIsNone(result["error"])


def run_tests():
    """Run all tests and print results."""
    print("=" * 70)
    print("Testing SharePoint Upload Implementation")
    print("=" * 70)
    print()

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestResolveFolderId))
    suite.addTests(loader.loadTestsFromTestCase(TestDownloadFile))
    suite.addTests(loader.loadTestsFromTestCase(TestUploadFileToSharePoint))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print()
    print("=" * 70)
    if result.wasSuccessful():
        print("✓ ALL TESTS PASSED")
        print(f"  Ran {result.testsRun} tests successfully")
    else:
        print("✗ SOME TESTS FAILED")
        print(f"  Failures: {len(result.failures)}")
        print(f"  Errors: {len(result.errors)}")
    print("=" * 70)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
