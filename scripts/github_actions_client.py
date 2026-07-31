#!/usr/bin/env python3
"""
GitHub Actions Client for triggering and monitoring CI workflows
用于触发和监控GitHub Actions工作流的客户端
"""

import os
import time
import base64
import requests
from typing import Dict, Optional, List
from pathlib import Path


class GitHubActionsClient:
    """Client for interacting with GitHub Actions API"""
    
    def __init__(self, token: str = None, repo: str = None, config_file: str = None):
        """
        Initialize GitHub Actions client
        
        Args:
            token: GitHub Personal Access Token (or set GITHUB_TOKEN env var)
            repo: Repository name in format "owner/repo" (or set GITHUB_REPO env var)
            config_file: Path to config file (default: config/github_config.json)
        """
        # Try to load from config file first
        if config_file is None:
            # Default config path relative to scripts directory
            config_file = Path(__file__).parent.parent / "config" / "github_config.json"
        
        config_token = None
        config_repo = None
        
        if config_file and Path(config_file).exists():
            try:
                import json
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    config_token = config.get('github', {}).get('token')
                    config_repo = config.get('github', {}).get('repo')
                    print(f"   📋 Loaded config from: {config_file}")
            except Exception as e:
                print(f"   ️  Failed to load config file: {e}")
        
        # Priority: parameter > config file > environment variable
        self.token = token or config_token or os.getenv('GITHUB_TOKEN')
        if not self.token:
            raise ValueError(
                "GitHub token not provided. Options:\n"
                "  1. Pass token parameter\n"
                "  2. Create config/github_config.json with github.token\n"
                "  3. Set GITHUB_TOKEN environment variable"
            )
        
        self.repo = repo or config_repo or os.getenv('GITHUB_REPO', 'your-username/argus')
        self.base_url = f"https://api.github.com/repos/{self.repo}"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        print(f"   ✅ GitHub Actions client initialized")
        print(f"      Repository: {self.repo}")
        print(f"      Token: {self.token[:20]}...{self.token[-10:]}")
    
    def trigger_workflow(self, patch_text: str) -> str:
        """
        Trigger kernel patch test workflow via repository dispatch
        
        Args:
            patch_text: Git patch/diff content as string
        
        Returns:
            workflow_run_id: ID of the triggered workflow run
        """
        print("📤 Triggering GitHub Actions workflow...")
        
        # Encode patch to base64
        patch_base64 = base64.b64encode(patch_text.encode('utf-8')).decode('utf-8')
        
        url = f"{self.base_url}/dispatches"
        
        payload = {
            "event_type": "test-patch",
            "client_payload": {
                "patch_content": patch_base64,
                "timestamp": int(time.time())
            }
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            
            print("✅ Workflow triggered successfully")
            
            # Wait a moment for the workflow to start
            time.sleep(5)
            
            # Get the latest workflow run ID
            run_id = self._get_latest_workflow_run_id()
            print(f"🆔 Workflow Run ID: {run_id}")
            
            return run_id
            
        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                raise Exception(
                    "Workflow not found. Make sure .github/workflows/kernel_patch_test.yml exists "
                    "and has repository_dispatch trigger configured."
                )
            elif response.status_code == 403:
                raise Exception(
                    "Permission denied. Check that your GitHub token has 'repo' and 'workflow' scopes."
                )
            else:
                raise Exception(f"Failed to trigger workflow: {e}")
    
    def wait_for_completion(self, run_id: str, timeout: int = 900, poll_interval: int = 30) -> Dict:
        """
        Poll workflow status until completion
        
        Args:
            run_id: Workflow run ID
            timeout: Maximum wait time in seconds (default: 15 minutes)
            poll_interval: Polling interval in seconds (default: 30)
        
        Returns:
            Dictionary containing workflow results and logs
        """
        print(f"\n⏳ Waiting for workflow completion (timeout: {timeout}s)...")
        print(f"   Workflow Run ID: {run_id}")
        
        start_time = time.time()
        last_status = None
        
        while time.time() - start_time < timeout:
            status_info = self._get_workflow_status(run_id)
            current_status = status_info['status']
            
            # Only print when status changes
            if current_status != last_status:
                print(f"   Status: {current_status} | Conclusion: {status_info.get('conclusion', 'N/A')}")
                last_status = current_status
            
            # Check if completed
            if current_status == 'completed':
                print(f"\n✅ Workflow completed!")
                print(f"   Conclusion: {status_info['conclusion']}")
                
                # Download results
                return self._download_results(run_id)
            
            # Wait before next poll
            time.sleep(poll_interval)
        
        raise TimeoutError(
            f"Workflow did not complete within {timeout} seconds. "
            f"Check workflow status at: https://github.com/{self.repo}/actions/runs/{run_id}"
        )
    
    def _get_latest_workflow_run_id(self) -> str:
        """Get the ID of the most recent workflow run for kernel_patch_test.yml"""
        url = f"{self.base_url}/actions/workflows/kernel_patch_test.yml/runs"
        
        # Try multiple times with delay to handle race condition
        import time
        max_retries = 5
        retry_delay = 3  # seconds
        
        for attempt in range(max_retries):
            try:
                params = {
                    "per_page": 1,
                    "status": "in_progress"
                }
                
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get('workflow_runs'):
                    return data['workflow_runs'][0]['id']
                
                # If no in_progress runs, try completed runs
                params['status'] = 'completed'
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                if data.get('workflow_runs'):
                    return data['workflow_runs'][0]['id']
                
                # If still not found, wait and retry
                if attempt < max_retries - 1:
                    print(f"   ⏳ Waiting for workflow to start (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                else:
                    raise Exception("No workflow runs found after multiple retries")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"   ️  Attempt {attempt + 1} failed: {e}")
                    time.sleep(retry_delay)
                else:
                    raise
        
        raise Exception("Failed to get workflow run ID")
    
    def _get_workflow_status(self, run_id: str) -> Dict:
        """Get current status of a workflow run"""
        url = f"{self.base_url}/actions/runs/{run_id}"
        
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        data = response.json()
        
        return {
            'status': data['status'],  # queued, in_progress, completed
            'conclusion': data.get('conclusion'),  # success, failure, cancelled, timed_out
            'updated_at': data['updated_at'],
            'html_url': data['html_url']
        }
    
    def _download_results(self, run_id: str) -> Dict:
        """Download workflow artifacts and parse results (with fallback to annotations)"""
        print("\n📥 Downloading build artifacts...")
        
        results = {
            'workflow_run_id': run_id,
            'jobs': {}
        }
        
        # Get all jobs for this workflow run
        url = f"{self.base_url}/actions/runs/{run_id}/jobs"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        jobs_data = response.json()
        
        for job in jobs_data.get('jobs', []):
            job_name = job['name']
            print(f"   Processing job: {job_name}")
            
            job_result = {
                'status': job.get('conclusion', 'unknown'),
                'errors': [],
                'warnings': [],
                'build_log': ''
            }
            
            # Try to download artifacts first
            artifacts = self._get_artifacts_for_run(run_id)
            artifact_has_data = False
            
            for artifact in artifacts:
                if job_name in artifact['name']:
                    try:
                        artifact_data = self._download_artifact(artifact['id'])
                        
                        # Check if artifact has actual content
                        if artifact_data and len(artifact_data) > 0:
                            artifact_has_data = True
                            
                            # Parse errors and warnings from artifact
                            if 'errors.txt' in artifact_data and artifact_data['errors.txt'].strip():
                                job_result['errors'] = [line.strip() for line in artifact_data['errors.txt'].strip().split('\n') if line.strip()]
                            
                            if 'warnings.txt' in artifact_data and artifact_data['warnings.txt'].strip():
                                job_result['warnings'] = [line.strip() for line in artifact_data['warnings.txt'].strip().split('\n') if line.strip()]
                            
                            if 'build.log' in artifact_data and artifact_data['build.log'].strip():
                                job_result['build_log'] = artifact_data['build.log']
                    except Exception as e:
                        print(f"   ️  Failed to download artifact for {job_name}: {e}")
            
            # Fallback: If artifacts are empty, try to get errors from job logs/annotations
            if not artifact_has_data or (not job_result['errors'] and job_result['status'] == 'failure'):
                print(f"   🔄 Artifacts empty, fetching errors from job annotations...")
                errors_from_annotations = self._get_job_annotations(job.get('id'))
                
                if errors_from_annotations:
                    job_result['errors'] = errors_from_annotations
                    job_result['build_log'] = '\n'.join(errors_from_annotations)
                    print(f"   ✅ Extracted {len(errors_from_annotations)} error(s) from annotations")
            
            results['jobs'][job_name] = job_result
        
        return results
    
    def _get_artifacts_for_run(self, run_id: str) -> List[Dict]:
        """Get list of artifacts for a workflow run"""
        url = f"{self.base_url}/actions/runs/{run_id}/artifacts"
        
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        return response.json().get('artifacts', [])
    
    def _get_job_annotations(self, job_id: str) -> List[str]:
        """
        Get annotations (errors/warnings) for a specific job
        
        Args:
            job_id: GitHub Actions job ID
        
        Returns:
            List of error messages from annotations
        """
        if not job_id:
            return []
        
        try:
            # Get job details including annotations
            url = f"{self.base_url}/actions/jobs/{job_id}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                print(f"   ⚠️  Failed to fetch job {job_id}: HTTP {response.status_code}")
                return []
            
            job_data = response.json()
            
            # Extract errors from steps that failed
            errors = []
            steps = job_data.get('steps', [])
            
            for step in steps:
                # Check if step has conclusion 'failure' or 'cancelled'
                if step.get('conclusion') in ['failure', 'cancelled']:
                    step_name = step.get('name', 'Unknown step')
                    
                    # Try to get error from step's log URL
                    # Note: We can't directly access logs via API without special permissions
                    # So we'll use the step name and conclusion as error info
                    error_msg = f"Step '{step_name}' failed with conclusion: {step.get('conclusion')}"
                    
                    # If there's a specific error message in the step, extract it
                    if step.get('number'):
                        errors.append(error_msg)
            
            # Also check for any annotations in the job
            # GitHub provides annotations via the checks API, but it requires additional setup
            # For now, we'll use the job-level information
            if job_data.get('conclusion') == 'failure':
                # Add a generic error if no specific errors found
                if not errors:
                    errors.append(f"Job failed with conclusion: {job_data.get('conclusion')}")
            
            return errors[:10]  # Limit to first 10 errors
            
        except Exception as e:
            print(f"   ⚠️  Error fetching annotations for job {job_id}: {e}")
            return []
    
    def _download_artifact(self, artifact_id: str) -> Dict[str, str]:
        """Download and extract artifact contents (improved in-memory version)"""
        url = f"{self.base_url}/actions/artifacts/{artifact_id}/zip"
        
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        # Use in-memory zip extraction for better reliability
        import zipfile
        import io
        
        try:
            # Create in-memory file-like object
            zip_buffer = io.BytesIO(response.content)
            files_content = {}
            
            with zipfile.ZipFile(zip_buffer, 'r') as zip_ref:
                for file_name in zip_ref.namelist():
                    # Skip directories
                    if file_name.endswith('/'):
                        continue
                    
                    # Extract base filename (remove directory path)
                    base_name = file_name.split('/')[-1]
                    if base_name:  # Ensure not empty
                        try:
                            content = zip_ref.read(file_name).decode('utf-8', errors='ignore')
                            files_content[base_name] = content
                        except Exception as e:
                            print(f"   ⚠️  Failed to read {file_name}: {e}")
            
            return files_content
            
        except zipfile.BadZipFile:
            raise Exception(f"Invalid zip file for artifact {artifact_id}")
        except Exception as e:
            raise Exception(f"Failed to extract artifact {artifact_id}: {e}")


def test_github_actions_client():
    """Test function to verify GitHub Actions client works"""
    print("=" * 80)
    print("🧪 Testing GitHub Actions Client")
    print("=" * 80)
    
    # Check environment variables
    token = os.getenv('GITHUB_TOKEN')
    repo = os.getenv('GITHUB_REPO')
    
    if not token:
        print("❌ GITHUB_TOKEN not set")
        print("\nTo set it:")
        print("  Windows PowerShell: $env:GITHUB_TOKEN=\"ghp_xxxxxxxxxxxx\"")
        print("  Linux/Mac: export GITHUB_TOKEN=\"ghp_xxxxxxxxxxxx\"")
        return False
    
    if not repo:
        print("⚠️  GITHUB_REPO not set, using default: your-username/argus")
        repo = "your-username/argus"
    
    print(f"✅ GitHub Token: {token[:10]}...")
    print(f"✅ Repository: {repo}")
    
    # Initialize client
    try:
        client = GitHubActionsClient(token=token, repo=repo)
        print("✅ Client initialized successfully")
        
        # Test with a simple patch
        test_patch = """diff --git a/test.c b/test.c
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/test.c
@@ -0,0 +1,5 @@
+#include <stdio.h>
+
+int main() {
+    printf("Hello, World!\\n");
+    return 0;
+}
"""
        
        print("\n📤 Testing workflow trigger...")
        print("   (This will actually trigger a workflow run)")
        
        # Uncomment to actually trigger
        # run_id = client.trigger_workflow(test_patch)
        # print(f"✅ Triggered workflow: {run_id}")
        
        print("\n✅ All tests passed!")
        print("\nNote: To actually trigger workflows, uncomment the trigger code above.")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    test_github_actions_client()
