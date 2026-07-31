#!/usr/bin/env python3
"""
Argus Code Review Pipeline - Complete 3-stage workflow
完整的三阶段代码审查管道

Stages:
1. Local Static Analysis (checkpatch, AST, metrics)
2. GitHub Actions CI Testing (cloud compilation)
3. LLM Diagnosis & Review (AI-powered analysis)
"""

import sys
import os
from pathlib import Path
from typing import Dict, Optional

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from kernel_self_check import KernelSelfCheckEngine
from ast_analyzer_enhanced import enhanced_ast_analysis
from rag_retriever import RAGRetriever
from llm_reviewer import LLMReviewer
from github_actions_client import GitHubActionsClient
from ci_log_parser import CILogParser


class ArgusCodeReviewPipeline:
    """
    Complete 3-stage code review pipeline for Linux kernel patches.
    
    Stages:
    1. Local Static Analysis (checkpatch, maintainers, AST, metrics)
    2. GitHub Actions CI Testing (cloud-based compilation matrix)
    3. LLM Diagnosis & Review (AI-powered analysis with full context)
    """
    
    def __init__(self, kernel_dir: str = "./linux"):
        """
        Initialize all pipeline components.
        
        Args:
            kernel_dir: Path to Linux kernel source tree
        """
        self.kernel_dir = kernel_dir
        
        # Initialize engines
        print("🔧 Initializing Argus Pipeline...")
        self.self_check = KernelSelfCheckEngine(kernel_dir)
        print("✅ Self-check engine initialized")
        print("✅ AST analyzer ready")
        
        # Initialize RAG retriever
        try:
            self.rag_retriever = RAGRetriever()
            print("✅ RAG retriever initialized")
        except Exception as e:
            print(f"⚠️  RAG retriever initialization failed: {e}")
            self.rag_retriever = None
        
        # Initialize LLM reviewer
        try:
            self.llm_reviewer = LLMReviewer()
            if self.llm_reviewer.model:
                print("✅ LLM reviewer initialized")
            else:
                print("⚠️  LLM model not loaded, will use prompt-only mode")
        except Exception as e:
            print(f"⚠️  LLM reviewer initialization failed: {e}")
            self.llm_reviewer = None
    
    def run_full_review(self, patch_text: str, patch_file_path: Optional[str] = None) -> Dict:
        """
        Execute complete 3-stage review pipeline.
        
        Args:
            patch_text: Git diff/patch content as string
            patch_file_path: Path to patch file (optional, required for Stage 1 checks)
        
        Returns:
            Complete review report dictionary
        """
        print("\n" + "=" * 80)
        print("🚀 ARGUS CODE REVIEW PIPELINE - STARTING")
        print("=" * 80)
        
        report = {
            'patch': patch_text,
            'patch_file': patch_file_path,
            'stages': {},
            'final_verdict': None,
            'pipeline_status': 'running'
        }
        
        try:
            # ===== Stage 1: Local Static Analysis =====
            print("\n📋 [Stage 1/3] Local Static Analysis...")
            stage1_result = self._run_stage_1_static_analysis(patch_text, patch_file_path)
            report['stages']['static_analysis'] = stage1_result
            
            # Early termination if checkpatch fails
            compliance_checkpatch = stage1_result.get('compliance', {}).get('checkpatch', {})
            if compliance_checkpatch.get('status') == 'FAIL':
                report['final_verdict'] = "❌ BLOCKED: Fix checkpatch errors first"
                report['pipeline_status'] = 'blocked_at_stage_1'
                print(f"\n{report['final_verdict']}")
                return report
            
            # ===== Stage 2: GitHub Actions CI Testing =====
            print("\n☁️  [Stage 2/3] GitHub Actions CI Testing...")
            stage2_result = self._run_stage_2_github_actions(patch_text)
            report['stages']['ci_testing'] = stage2_result
            
            # Note: Don't early terminate on CI failure
            # Continue to LLM for comprehensive analysis
            if stage2_result.get('compilation', {}).get('status') == 'FAIL':
                print(f"\n⚠️  WARNING: Compilation failed, but continuing to LLM analysis...")
            
            # ===== Stage 3: LLM Diagnosis & Review =====
            print("\n🤖 [Stage 3/3] LLM Diagnosis & Review...")
            stage3_result = self._run_stage_3_llm_review(
                patch_text, 
                stage1_result,  # AST + compliance
                stage2_result   # CI logs
            )
            report['stages']['llm_review'] = stage3_result
            
            # ===== Generate Final Verdict =====
            report['final_verdict'] = self._generate_final_verdict(report)
            report['pipeline_status'] = 'completed'
            
            print("\n" + "=" * 80)
            print(f"✅ PIPELINE COMPLETED: {report['final_verdict']}")
            print("=" * 80)
            
        except Exception as e:
            print(f"\n❌ Pipeline execution failed: {e}")
            import traceback
            traceback.print_exc()
            
            report['error'] = str(e)
            report['final_verdict'] = "❌ ERROR: Pipeline execution failed"
            report['pipeline_status'] = 'failed'
        
        return report
    
    def _run_stage_1_static_analysis(self, patch_text: str, patch_file_path: Optional[str]) -> Dict:
        """
        Stage 1: Run all static analysis checks
        
        Integrates:
        - Compliance checks (checkpatch, maintainer, sparse)
        - AST structural analysis
        - Software metrics calculation
        """
        result = {
            'status': 'completed',
            'compliance': {},
            'ast': {},
            'summary': ''
        }
        
        # Run compliance checks if patch file provided
        if patch_file_path:
            print("   Running compliance checks...")
            result['compliance'] = self.self_check.run_full_self_check(patch_file_path)
        else:
            print("   ⚠️  Skipping compliance checks (no patch file)")
            result['compliance'] = {'status': 'skipped'}
        
        # Run AST analysis
        print("   Running AST analysis...")
        result['ast'] = enhanced_ast_analysis(patch_text, kernel_dir=self.kernel_dir)
        
        # Generate summary
        comp_status = result['compliance'].get('checkpatch', {}).get('status', 'N/A')
        ast_funcs = len(result['ast'].get('functions', []))
        result['summary'] = f"Compliance: {comp_status}, AST Functions: {ast_funcs}"
        
        return result
    
    def _run_stage_2_github_actions(self, patch_text: str) -> Dict:
        """
        Stage 2: Trigger GitHub Actions for cloud-based CI testing
        
        This replaces local compilation with cloud-based testing.
        No local kernel source required!
        """
        try:
            # Initialize clients
            gh_client = GitHubActionsClient()
            log_parser = CILogParser()
            
            # Trigger workflow
            print("   📤 Triggering GitHub Actions workflow...")
            run_id = gh_client.trigger_workflow(patch_text)
            print(f"   ✅ Workflow triggered: {run_id}")
            
            # Wait for completion (timeout: 15 minutes)
            print("   ⏳ Waiting for workflow completion...")
            workflow_results = gh_client.wait_for_completion(
                run_id, 
                timeout=900,  # 15 minutes
                poll_interval=30
            )
            
            # Parse results
            print("   📊 Parsing CI results...")
            ci_result = log_parser.parse_workflow_results(workflow_results)
            
            return ci_result
            
        except Exception as e:
            print(f"   ❌ GitHub Actions CI failed: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'status': 'error',
                'patch_apply': {'success': False, 'message': str(e)},
                'compilation': {
                    'status': 'UNKNOWN',
                    'errors': [str(e)],
                    'warnings': [],
                    'log': ''
                },
                'summary': f'CI execution failed: {str(e)}'
            }
    
    def _run_stage_3_llm_review(self, patch_text: str, stage1_result: Dict, stage2_result: Dict) -> Dict:
        """
        Stage 3: LLM-based review generation with full context
        
        Integrates:
        - Patch diff text
        - Stage 1 results (AST + compliance)
        - Stage 2 results (CI logs)
        - RAG historical contexts
        """
        if not self.llm_reviewer:
            print("   ⚠️  LLM reviewer not available")
            return {
                'status': 'unavailable',
                'review': None,
                'message': 'LLM reviewer not initialized'
            }
        
        try:
            # Extract components from Stage 1
            ast_result = stage1_result.get('ast', {})
            
            # Run RAG retrieval
            print("   🔎 Retrieving RAG contexts...")
            rag_result = self._run_rag_retrieval(patch_text, ast_result)
            rag_contexts = rag_result.get('contexts', []) if rag_result.get('status') == 'completed' else []
            
            # Construct prompt with all context
            ci_result = stage2_result if stage2_result.get('status') == 'completed' else None
            prompt = self.llm_reviewer.construct_review_prompt(
                patch_text, 
                ast_result, 
                rag_contexts,
                ci_result
            )
            
            # Generate review
            print("   🤖 Generating LLM review...")
            review_result = self.llm_reviewer.generate_review(prompt, max_new_tokens=512)
            
            return {
                'status': review_result['status'],
                'review_text': review_result.get('review_text'),
                'parsed': review_result.get('parsed'),
                'prompt_length': len(prompt),
                'inference_time': review_result.get('inference_time_seconds')
            }
        except Exception as e:
            print(f"   ⚠️  LLM review failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'review': None,
                'error': str(e)
            }
    
    def _run_rag_retrieval(self, patch_text: str, ast_result: Dict) -> Dict:
        """Helper method for RAG retrieval (extracted from old Stage 4)"""
        if not self.rag_retriever:
            print("   ⚠️  RAG retriever not available")
            return {
                'status': 'unavailable',
                'contexts': [],
                'message': 'RAG retriever not initialized'
            }
        
        try:
            # Build enhanced query with AST metadata
            enhanced_query = self.rag_retriever.build_enhanced_query(patch_text, ast_result)
            
            # Search for similar contexts
            contexts = self.rag_retriever.search(enhanced_query, top_k=3)
            
            return {
                'status': 'completed',
                'contexts': contexts,
                'query_length': len(enhanced_query),
                'context_count': len(contexts)
            }
        except Exception as e:
            print(f"   ⚠️  RAG retrieval failed: {e}")
            return {
                'status': 'error',
                'contexts': [],
                'error': str(e)
            }
    
    def _generate_final_verdict(self, report: Dict) -> str:
        """
        Generate final verdict based on all stage results.
        
        Priority order:
        1. CI compilation failures (blocker)
        2. Checkpatch failures (blocker)
        3. LLM severity assessment
        4. Default: Ready to submit
        """
        stages = report['stages']
        
        # Check CI compilation failures (critical blocker)
        ci_result = stages.get('ci_testing', {})
        if ci_result.get('status') == 'completed':
            # Compilation failure is a hard blocker
            if ci_result.get('compilation', {}).get('status') == 'FAIL':
                error_count = len(ci_result['compilation'].get('errors', []))
                return f"❌ REJECTED: Compilation failed with {error_count} errors"
        
        # Check checkpatch failures (blocker)
        static_analysis = stages.get('static_analysis', {})
        compliance = static_analysis.get('compliance', {})
        if compliance.get('checkpatch', {}).get('status') == 'FAIL':
            error_count = compliance['checkpatch'].get('error_count', 0)
            return f"❌ REJECTED: {error_count} checkpatch errors found"
        
        # Check LLM severity (if available)
        llm_result = stages.get('llm_review', {})
        if llm_result.get('status') == 'completed' and llm_result.get('parsed'):
            severity = llm_result['parsed'].get('severity', '')
            
            severity_map = {
                'Critical': "⚠️  NEEDS FIX: Critical issues found",
                'Warning': "⚠️  SUGGESTED CHANGES: Warnings detected",
                'Suggestion': "✅ ACCEPTABLE: Minor suggestions only",
                'Info': "✅ READY TO SUBMIT"
            }
            
            verdict = severity_map.get(severity, "✅ READY TO SUBMIT")
            return verdict
        
        # Default verdict
        return "✅ READY TO SUBMIT (basic checks passed)"
    
    def save_report(self, report: Dict, output_path: str = "review_report.json"):
        """Save review report to JSON file"""
        import json
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n💾 Report saved to: {output_path}")


def main():
    """Test the pipeline with a sample patch or user-provided patch file"""
    import sys
    
    # Check if user provided a patch file as argument
    if len(sys.argv) > 1:
        patch_file = sys.argv[1]
        print(f"📄 Using user-provided patch: {patch_file}")
        
        # Read the patch file
        with open(patch_file, 'r') as f:
            sample_patch = f.read()
    else:
        # Use built-in sample patch for testing
        sample_patch = """From: John Doe <john@example.com>
Date: Mon, 1 Jan 2024 12:00:00 +0000
Subject: [PATCH] net: tcp: Fix null pointer dereference in tcp_v4_rcv

This patch fixes a potential null pointer dereference when handling
malformed TCP packets.

Signed-off-by: John Doe <john@example.com>
---
 net/ipv4/tcp_input.c | 5 ++++-
 1 file changed, 4 insertions(+), 1 deletion(-)

diff --git a/net/ipv4/tcp_input.c b/net/ipv4/tcp_input.c
index 1234567..abcdefg 100644
--- a/net/ipv4/tcp_input.c
+++ b/net/ipv4/tcp_input.c
@@ -3500,7 +3500,10 @@ int tcp_v4_rcv(struct sk_buff *skb)
        struct sock *sk = skb->sk;
        const struct iphdr *iph = ip_hdr(skb);
        
-       if (!sk)
+       if (!sk) {
+               kfree_skb(skb);
                return NET_RX_DROP;
+       }
        
        /* Process packet */
        tcp_rcv_established(sk, skb);
-- 
2.39.0
"""
        
        # Save sample patch
        patch_file = "test_pipeline.patch"
        with open(patch_file, 'w') as f:
            f.write(sample_patch)
        
        print(f"✅ Created test patch: {patch_file}")
    
    # Initialize pipeline
    pipeline = ArgusCodeReviewPipeline(kernel_dir="./linux")
    
    # Run full review
    report = pipeline.run_full_review(sample_patch, patch_file_path=patch_file)
    
    # Save report
    pipeline.save_report(report, "test_pipeline_report.json")
    
    # Cleanup (only remove auto-generated test files)
    if patch_file == "test_pipeline.patch":
        os.remove(patch_file)
        print("\n🗑️  Cleaned up test files")
    else:
        print(f"\nℹ️  Keeping user-provided patch: {patch_file}")


if __name__ == "__main__":
    main()
