#!/usr/bin/env python3
"""
LLM Reviewer for Argus Pipeline
独立的LLM推理引擎，可从Pipeline直接调用
"""

import os
from pathlib import Path
from typing import Dict, Optional

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from peft import PeftModel
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("⚠️  Warning: transformers/peft not available")


class LLMReviewer:
    """
    LLM-based code reviewer using fine-tuned RAFT model.
    Generates structured code review reports.
    """
    
    def __init__(self, model_path: str = None):
        """
        Initialize LLM reviewer.
        
        Args:
            model_path: Path to LoRA adapter (optional)
        """
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "transformers, peft, and bitsandbytes are required. "
                "Install with: pip install transformers peft bitsandbytes"
            )
        
        # Default model path
        if model_path is None:
            model_path = Path(__file__).parent.parent / "models" / "argus_raft_lora_1.5b"
        
        self.model_path = str(model_path)
        self.base_model_name = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
        self.model = None
        self.tokenizer = None
        
        self._initialize()
    
    def _initialize(self):
        """Load RAFT fine-tuned model"""
        print("🔧 Initializing LLM Reviewer...")
        
        if not os.path.exists(self.model_path):
            print(f"   ⚠️  LoRA adapter not found at: {self.model_path}")
            print("   Please train the model first or provide the adapter path.")
            return
        
        try:
            print(f"   Loading base model: {self.base_model_name}")
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_name)
            self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Configure 4-bit quantization
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=False,
            )
            
            # Determine device
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"   Using device: {device}")
            
            # Load base model
            base_model = AutoModelForCausalLM.from_pretrained(
                self.base_model_name,
                quantization_config=bnb_config if device == "cuda" else None,
                device_map=device if device == "cuda" else "cpu",
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )
            
            # Load LoRA adapter
            print("   Loading LoRA adapter...")
            self.model = PeftModel.from_pretrained(base_model, self.model_path)
            self.model.eval()
            
            print(f"   ✅ RAFT model loaded successfully!")
            print(f"   Device: {next(self.model.parameters()).device}")
            
        except Exception as e:
            print(f"   ⚠️  Error loading RAFT model: {e}")
            import traceback
            traceback.print_exc()
            self.model = None
            self.tokenizer = None
    
    def generate_review(self, prompt: str, max_new_tokens: int = 512) -> Dict:
        """
        Generate code review using the fine-tuned RAFT model.
        
        Args:
            prompt: Constructed review prompt
            max_new_tokens: Maximum tokens to generate
        
        Returns:
            Dictionary containing review result
        """
        if self.model is None or self.tokenizer is None:
            return {
                'status': 'unavailable',
                'message': 'LLM model not loaded',
                'review_text': None,
                'parsed': None
            }
        
        print(f"   🤖 Generating review (max_tokens={max_new_tokens})...")
        
        try:
            import time
            start_time = time.time()
            
            # Tokenize input
            device = next(self.model.parameters()).device
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048).to(device)
            
            # Generate
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    min_new_tokens=10,
                    temperature=0.7,
                    do_sample=True,
                    top_p=0.9,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                    repetition_penalty=1.1,
                )
            
            # Decode output
            generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Extract only the generated part (after the prompt)
            review_text = generated_text[len(prompt):].strip()
            
            inference_time = time.time() - start_time
            print(f"   ✅ Review generated in {inference_time:.2f}s")
            
            # Parse structured output
            parsed_result = self._parse_review_output(review_text)
            
            return {
                'status': 'success',
                'review_text': review_text,
                'parsed': parsed_result,
                'inference_time_seconds': round(inference_time, 2),
                'tokens_generated': len(self.tokenizer.encode(review_text))
            }
            
        except Exception as e:
            print(f"   ❌ Review generation failed: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'status': 'error',
                'message': str(e),
                'review_text': None,
                'parsed': None
            }
    
    def _parse_review_output(self, text: str) -> Dict:
        """
        Parse structured review output into components.
        
        Expected format:
        ##Reason: ...
        ##Issue: ...
        ##Severity: ...
        ##Suggestion: ...
        """
        result = {
            'reason': '',
            'issue': '',
            'severity': '',
            'suggestion': ''
        }
        
        lines = text.split('\n')
        current_key = None
        current_value = []
        
        for line in lines:
            if line.startswith('##Reason:'):
                current_key = 'reason'
                current_value = [line.replace('##Reason:', '').strip()]
            elif line.startswith('##Issue:'):
                if current_key:
                    result[current_key] = '\n'.join(current_value).strip()
                current_key = 'issue'
                current_value = [line.replace('##Issue:', '').strip()]
            elif line.startswith('##Severity:'):
                if current_key:
                    result[current_key] = '\n'.join(current_value).strip()
                current_key = 'severity'
                current_value = [line.replace('##Severity:', '').strip()]
            elif line.startswith('##Suggestion:'):
                if current_key:
                    result[current_key] = '\n'.join(current_value).strip()
                current_key = 'suggestion'
                current_value = [line.replace('##Suggestion:', '').strip()]
            elif current_key and line.strip():
                current_value.append(line.strip())
        
        # Save last key
        if current_key:
            result[current_key] = '\n'.join(current_value).strip()
        
        return result
    
    def construct_review_prompt(self, patch: str, ast_metadata: Dict, 
                                 rag_contexts: list, ci_results: Dict = None) -> str:
        """
        Construct enhanced prompt for LLM review.
        
        Args:
            patch: Git diff/patch content
            ast_metadata: AST analysis results
            rag_contexts: Retrieved similar contexts from RAG
            ci_results: CI test results (optional)
        
        Returns:
            Constructed prompt string
        """
        prompt_parts = []
        
        # System instruction
        prompt_parts.append("You are an expert Linux kernel reviewer with deep knowledge of C programming, security, and code quality.")
        prompt_parts.append("Analyze the provided code patch using the AST analysis and historical review contexts.")
        prompt_parts.append("")
        
        # Patch content
        prompt_parts.append("=" * 60)
        prompt_parts.append("CODE PATCH TO REVIEW")
        prompt_parts.append("=" * 60)
        prompt_parts.append(patch)
        prompt_parts.append("")
        
        # AST metadata
        if ast_metadata and ast_metadata.get('metadata_text'):
            prompt_parts.append("=" * 60)
            prompt_parts.append("AST ANALYSIS RESULTS")
            prompt_parts.append("=" * 60)
            prompt_parts.append(ast_metadata['metadata_text'])
            
            if ast_metadata.get('functions'):
                prompt_parts.append("")
                prompt_parts.append("Detailed Function Information:")
                for func in ast_metadata['functions'][:3]:
                    prompt_parts.append(
                        f"  - {func['function_name']}(): "
                        f"return={func.get('return_type', 'N/A')}, "
                        f"params={func['param_count']}, "
                        f"lines={func['line_count']}, "
                        f"complexity={func['cyclomatic_complexity']}"
                    )
                    if func.get('potential_issues'):
                        prompt_parts.append(f"    ⚠️  Issues: {', '.join(func['potential_issues'][:2])}")
            
            prompt_parts.append("")
        
        # RAG contexts
        if rag_contexts:
            prompt_parts.append("=" * 60)
            prompt_parts.append("HISTORICAL REVIEW CONTEXTS")
            prompt_parts.append("=" * 60)
            prompt_parts.append("The following are similar code reviews from the Linux kernel mailing list.")
            prompt_parts.append("Use them as reference, but focus on the current patch's specific issues.")
            prompt_parts.append("")
            
            for ctx in rag_contexts:
                similarity_pct = int(ctx.get('similarity', 0) * 100)
                
                if ctx['rank'] == 1 and similarity_pct >= 80:
                    relevance = "HIGHLY RELEVANT"
                elif similarity_pct >= 60:
                    relevance = "MODERATELY RELEVANT"
                else:
                    relevance = "LESS RELEVANT"
                
                prompt_parts.append(f"--- Context {ctx['rank']} ({relevance}, Similarity: {similarity_pct}%) ---")
                prompt_parts.append(ctx['document'])
                prompt_parts.append("")
        
        # CI test results (from GitHub Actions)
        if ci_results:
            prompt_parts.append("=" * 60)
            prompt_parts.append("CI TEST RESULTS (GitHub Actions)")
            prompt_parts.append("=" * 60)
            
            compilation = ci_results.get('compilation', {})
            if compilation:
                status = compilation.get('status', 'UNKNOWN')
                prompt_parts.append(f"Overall Status: {status}")
                
                # Show matrix results
                matrix = compilation.get('matrix_results', {})
                if matrix:
                    prompt_parts.append("\nBuild Matrix:")
                    for job_name, result in matrix.items():
                        icon = "✅" if result['status'] == 'success' else "❌"
                        prompt_parts.append(
                            f"  {icon} {job_name}: "
                            f"{result['error_count']} errors, "
                            f"{result['warning_count']} warnings"
                        )
                
                # Show errors
                errors = compilation.get('errors', [])
                if errors:
                    prompt_parts.append(f"\nCompilation Errors ({len(errors)}):")
                    for err in errors[:10]:
                        prompt_parts.append(f"  {err}")
                
                # Show warnings
                warnings = compilation.get('warnings', [])
                if warnings:
                    prompt_parts.append(f"\nCompilation Warnings ({len(warnings)}):")
                    for warn in warnings[:10]:
                        prompt_parts.append(f"  {warn}")
                
                if not errors and not warnings:
                    prompt_parts.append("\n✅ No compilation errors or warnings found!")
            
            prompt_parts.append("")
        
        # Output format requirement
        prompt_parts.append("=" * 60)
        prompt_parts.append("REVIEW OUTPUT FORMAT")
        prompt_parts.append("=" * 60)
        prompt_parts.append("")
        prompt_parts.append("You MUST provide your review in the EXACT following format. ALL FOUR FIELDS ARE REQUIRED:")
        prompt_parts.append("")
        prompt_parts.append("##Reason: [Your step-by-step reasoning process. Analyze the code logic, identify potential issues, consider edge cases. Be specific about what you found.]")
        prompt_parts.append("")
        prompt_parts.append("##Issue: [Clear description of the main issue(s) found. If no critical issues, state 'No major issues detected'. Must be a complete sentence.]")
        prompt_parts.append("")
        prompt_parts.append("##Severity: [Choose ONE from: Critical / Warning / Suggestion / Info]")
        prompt_parts.append("  - Critical: Security vulnerability, memory leak, null pointer dereference, use-after-free")
        prompt_parts.append("  - Warning: Logic error, performance issue, missing error handling, resource leak")
        prompt_parts.append("  - Suggestion: Code style improvement, minor optimization, best practice recommendation")
        prompt_parts.append("  - Info: General comment, documentation suggestion, no action needed")
        prompt_parts.append("")
        prompt_parts.append("##Suggestion: [Concrete, actionable fix recommendation. Include specific code changes or API calls to use. If suggesting code, show the corrected version.]")
        prompt_parts.append("")
        prompt_parts.append("EXAMPLE OUTPUT:")
        prompt_parts.append("---")
        prompt_parts.append("##Reason: The function tcp_v4_rcv checks if sk is NULL but doesn't free the skb buffer before returning. This causes a memory leak as the skb is never freed when sk is NULL.")
        prompt_parts.append("")
        prompt_parts.append("##Issue: Memory leak - skb buffer not freed when socket is NULL")
        prompt_parts.append("")
        prompt_parts.append("##Severity: Warning")
        prompt_parts.append("")
        prompt_parts.append("##Suggestion: Add kfree_skb(skb) call before returning NET_RX_DROP to properly free the buffer. Modified code:\nif (!sk) {\n    kfree_skb(skb);\n    return NET_RX_DROP;\n}")
        prompt_parts.append("---")
        prompt_parts.append("")
        prompt_parts.append("IMPORTANT RULES:")
        prompt_parts.append("1. You MUST include ALL FOUR fields (##Reason, ##Issue, ##Severity, ##Suggestion)")
        prompt_parts.append("2. Each field must have actual content - NO empty fields allowed")
        prompt_parts.append("3. ##Suggestion must be concrete and actionable - provide specific code or API recommendations")
        prompt_parts.append("4. Follow the exact format shown in the example above")
        prompt_parts.append("")
        prompt_parts.append("Now analyze the patch and provide your review:")
        
        return "\n".join(prompt_parts)


def test_llm_reviewer():
    """Test the LLM reviewer"""
    
    print("=" * 80)
    print("🧪 Testing LLM Reviewer")
    print("=" * 80)
    
    try:
        # Initialize reviewer
        reviewer = LLMReviewer()
        
        if reviewer.model is None:
            print("\n⚠️  Model not loaded, skipping generation test")
            return
        
        # Sample prompt
        sample_prompt = """
You are an expert Linux kernel reviewer.

============================================================
CODE PATCH TO REVIEW
============================================================
diff --git a/net/ipv4/tcp_input.c b/net/ipv4/tcp_input.c
@@ -3500,7 +3500,10 @@ int tcp_v4_rcv(struct sk_buff *skb)
        struct sock *sk = skb->sk;
        
-       if (!sk)
+       if (!sk) {
+               kfree_skb(skb);
                return NET_RX_DROP;
+       }

============================================================
REVIEW OUTPUT FORMAT
============================================================
##Reason: ...
##Issue: ...
##Severity: ...
##Suggestion: ...
"""
        
        # Generate review
        result = reviewer.generate_review(sample_prompt, max_new_tokens=256)
        
        print(f"\n✅ Review generated:")
        print(f"   Status: {result['status']}")
        print(f"   Inference time: {result.get('inference_time_seconds', 0):.2f}s")
        
        if result.get('parsed'):
            parsed = result['parsed']
            print(f"\n   Reason: {parsed.get('reason', '')[:100]}...")
            print(f"   Issue: {parsed.get('issue', '')[:100]}...")
            print(f"   Severity: {parsed.get('severity', '')}")
            print(f"   Suggestion: {parsed.get('suggestion', '')[:100]}...")
        
        print("\n" + "=" * 80)
        print("✅ LLM Reviewer test completed!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_llm_reviewer()
