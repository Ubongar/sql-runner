"""
test_runner.py
Automated integration testing for the sql-runner pipeline.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from app.main import run_pipeline
from app.llm_planner import rewrite_query, plan_and_generate
from app.sql_validator import validate_sql
from app.executor import run_query

TEST_SCENARIOS = [
    {
        "name": "Scenario 1: E-Commerce Multi-Table Join & BLOB inference",
        "files": ["test/test_01_customers.csv", "test/test_02_products.json", "test/test_03_orders.json", "test/test_04_order_items.csv"],
        "question": "Calculate total revenue per customer city including discounts, excluding cancelled orders.",
        "expect_feasible": True
    },
    {
        "name": "Scenario 2: HR Analytics Self-Join",
        "files": ["test/test_05_employees.csv"],
        "question": "List every manager's name and the total number of direct reports they manage.",
        "expect_feasible": True
    },
    {
        "name": "Scenario 3: HR Window Functions",
        "files": ["test/test_06_salary_history.json"],
        "question": "Find each employee's latest salary raise percentage compared to their previous salary.",
        "expect_feasible": True
    },
    {
        "name": "Scenario 4: Guardrail Test (Mutating Data)",
        "files": ["test/test_05_employees.csv"],
        "question": "Update Sarah Connor's base salary to 160000.",
        "expect_feasible": False 
    },
    {
        "name": "Scenario 5: University GPA Calculation",
        "files": ["test/test_09_courses.csv", "test/test_10_enrollments.json"],
        "question": "Calculate weighted GPA per student where A=4, B=3, C=2 weighted by course credits.",
        "expect_feasible": True
    },
    {
        "name": "Scenario 6: Logistics (CTEs, Window Functions, 4-Way Join)",
        "files": ["test/test_11_regions.csv", "test/test_12_drivers.csv", "test/test_13_vehicles.csv", "test/test_14_deliveries.csv"],
        "question": "Write a query using a CTE to calculate the total COMPLETED deliveries and avg time for each driver. Join with drivers and regions. Use a window function partitioned by region to find the #1 ranked driver in each region by deliveries. Return region_name, driver_name, total deliveries, and target_delivery_time.",
        "expect_feasible": True
    }
]

def run_tests():
    print("="*80)
    print("🚀 Starting 2FA SQL-Runner Integration Tests")
    print("="*80)

    passed = 0
    total = len(TEST_SCENARIOS)

    for i, scenario in enumerate(TEST_SCENARIOS, 1):
        print(f"\n[{i}/{total}] Testing: {scenario['name']}")
        print(f"Raw Request: {scenario['question']}")
        
        missing_files = [f for f in scenario['files'] if not os.path.exists(f)]
        if missing_files:
            print(f"  ❌ FAIL: Missing test files: {missing_files}")
            continue

        prep = run_pipeline(scenario['files'])
        if prep is False:
            print("  ❌ FAIL: Data ingestion or cleaning failed.")
            continue
        
        # FIX: Replaced cleaning_reports with '_' to fix the 'Unused variable' warning
        schemas, _, conn = prep
        
        rewritten = rewrite_query(schemas, scenario['question'])
        print(f"  -> Contextualized: {rewritten}")

        plan = plan_and_generate(schemas, rewritten)
        
        if plan.get("feasible") != scenario["expect_feasible"]:
            print(f"  ❌ FAIL: Expected feasible={scenario['expect_feasible']}, got {plan.get('feasible')}.")
            if not plan.get("feasible"):
                print(f"     Reason: {plan.get('reason')}")
            continue
            
        if not plan.get("feasible"):
            print("  ✅ PASS: Query correctly flagged as infeasible/blocked.")
            passed += 1
            continue

        # FIX: Added explicit string/list fallbacks
        sql = plan.get("sql") or ""
        tables_used = plan.get("tables_used") or []
        
        validation = validate_sql(sql, schemas, tables_used)
        if not validation.get("valid"):
            print(f"  ❌ FAIL: Generated SQL failed validation.")
            print(f"     SQL: {sql}")
            print(f"     Reason: {validation.get('reason')}")
            continue

        outcome = run_query(sql, conn)
        if not outcome.get("success"):
            print(f"  ❌ FAIL: SQL Execution error in DuckDB.")
            print(f"     SQL: {sql}")
            print(f"     Error: {outcome.get('error')}")
            continue

        # FIX: Ensure we are getting the length of a list, not None
        result_data = outcome.get("result") or []
        print(f"  ✅ PASS: Successfully executed. Returned {len(result_data)} rows.")
        passed += 1

    print("\n" + "="*80)
    print(f"🏁 Test Suite Completed: {passed}/{total} Passed")
    print("="*80)

if __name__ == "__main__":
    run_tests()