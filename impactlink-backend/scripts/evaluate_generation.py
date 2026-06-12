import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.scoring_agent import score_section

def evaluate_generation():
    print("👨‍⚖️ Starting LLM-as-a-Judge Evaluation (Generation Quality)\n")
    
    # Mock data to evaluate
    mock_grant = "California Urban Forestry Grant: Priority for heat island mitigation."
    mock_sec_title = "Executive Summary"
    mock_sec_content = "We will plant trees in East LA. It is very hot there. We hope this helps."
    
    print(f"--- Evaluating Section: {mock_sec_title} ---")
    print(f"Content: \"{mock_sec_content}\"")
    
    try:
        # Using the actual scoring agent implementation with correct signature
        result = score_section(
            section_key="exec_summary",
            section_title=mock_sec_title,
            content=mock_sec_content,
            grant={"title": "Urban Forestry", "agency": "CAL FIRE", "focus_areas": mock_grant},
            funder_vocab=["canopy", "heat island", "resilience"]
        )
        
        print(f"\n🏆 Score: {result['score']}/100")
        print(f"📝 Feedback: {result['feedback']}")
        
        if result['score'] < 75:
            print("⚠️ Result: Section needs reflection/rewrite.")
        else:
            print("✅ Result: High-quality draft.")
            
    except Exception as e:
        print(f"💥 Error during evaluation: {e}")

if __name__ == "__main__":
    evaluate_generation()
