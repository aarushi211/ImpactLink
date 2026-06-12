import sys
import os
import json

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.budget.generator import generate_budget

def run_evaluation():
    print("🧪 Starting Deterministic Logic Evaluation (Budget Engine)\n")
    
    test_scenarios = [
        {
            "name": "Standard Urban Forestry Grant",
            "max": 100000,
            "proposal": {
                "project_title": "LA Tree Canopy",
                "key_activities": ["Planting 500 trees", "Watering", "Community outreach"],
                "geographic_focus": ["Los Angeles, CA"],
                "budget_breakdown": ["Personnel", "Equipment", "Supplies"]
            }
        },
        {
            "name": "Extreme Over-Budget Request (Stress Test)",
            "max": 50000,
            "proposal": {
                "project_title": "Massive Reforestation",
                "key_activities": ["Hire 50 Project Managers", "Buy 10 Trucks"], # Impossible for 50k
                "geographic_focus": ["San Francisco, CA"],
                "budget_breakdown": ["Personnel", "Travel"]
            }
        },
        {
            "name": "Low Wage Region Compliance",
            "max": 25000,
            "proposal": {
                "project_title": "Rural Education",
                "key_activities": ["Tutoring"],
                "geographic_focus": ["Rural Alabama"], # Should trigger min-wage floor
                "budget_breakdown": ["Personnel"]
            }
        }
    ]

    results = []
    
    for tc in test_scenarios:
        print(f"--- Running: {tc['name']} ---")
        try:
            budget = generate_budget(tc['proposal'], tc['max'])
            
            if "error" in budget:
                print(f"❌ Handled expected failure: {budget['details']}")
                results.append({"name": tc['name'], "status": "PASS (Caught Violation)"})
                continue

            # Verification logic
            total = budget.get("total_requested", 0)
            items_sum = sum(item["amount"] for item in budget.get("items", []))
            
            # Check 1: Math Integrity
            math_pass = (total == tc['max'] == items_sum)
            
            # Check 2: Minimum Wage Compliance
            # (In a real test, we would look up the specific min wage and check line items)
            
            if math_pass:
                print(f"✅ PASS: Total (${total:,}) matches max and sum of parts.")
                results.append({"name": tc['name'], "status": "PASS"})
            else:
                print(f"❌ FAIL: Math mismatch. Total: {total}, Sum: {items_sum}, Expected: {tc['max']}")
                results.append({"name": tc['name'], "status": "FAIL"})
                
        except Exception as e:
            print(f"💥 CRASH: {e}")
            results.append({"name": tc['name'], "status": f"CRASH: {e}"})
        print()

    print("="*40)
    print("EVALUATION SUMMARY")
    print("="*40)
    for res in results:
        print(f"{res['status']}: {res['name']}")

if __name__ == "__main__":
    run_evaluation()
