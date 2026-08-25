"""
test_runner.py
Automated integration testing for the sql-runner pipeline.
Evaluates data cleaning, LLM SQL generation, validation guardrails, and execution.
"""

from dotenv import load_dotenv
load_dotenv()

import os
from app.main import run_pipeline
from app.llm_planner import plan_and_generate
from app.sql_validator import validate_sql
from app.executor import run_query

# Define the scenarios based on our new complex test files
TEST_SCENARIOS = [
    {
        "name": "Scenario 1: E-Commerce Multi-Table Join & BLOB inference",
        "files": [
            "test/test_01_customers.csv",
            "test/test_02_products.json",
            "test/test_03_orders.json",
            "test/test_04_order_items.csv"
        ],
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
        "expect_feasible": False # The planner or validator MUST reject this
    },
    {
        "name": "Scenario 5: University GPA Calculation",
        "files": ["test/test_09_courses.csv", "test/test_10_enrollments.json"],
        "question": "Calculate weighted GPA per student where A=4, B=3, C=2 weighted by course credits.",
        "expect_feasible": True
    },
    {
        "name": "Scenario 6: Logistics (CTEs, Window Functions, 4-Way Join)",
        "files": [
            "test/test_11_regions.csv",
            "test/test_12_drivers.csv",
            "test/test_13_vehicles.csv",
            "test/test_14_deliveries.csv"
        ],
        "question": (
            "Write a query using a CTE (WITH clause) to calculate the total number of COMPLETED deliveries "
            "and the average delivery time for each driver. Then, join that CTE with the drivers and regions tables. "
            "Finally, use a window function (like RANK or DENSE_RANK) partitioned by region to find the #1 ranked "
            "driver in each region based on their total completed deliveries. Return the region_name, driver_name, "
            "total deliveries, and the region's target_delivery_time_mins."
        ),
        "expect_feasible": True
    }
]

def run_tests():
    print("="*60)
    print("🚀 Starting SQL-Runner Integration Tests")
    print("="*60)

    passed = 0
    total = len(TEST_SCENARIOS)

    for i, scenario in enumerate(TEST_SCENARIOS, 1):
        print(f"\n[{i}/{total}] Testing: {scenario['name']}")
        print(f"Question: {scenario['question']}")
        
        # Step 1: Check if files exist
        missing_files = [f for f in scenario['files'] if not os.path.exists(f)]
        if missing_files:
            print(f"  ❌ FAIL: Missing test files: {missing_files}")
            continue

        # Step 2: Pipeline setup (Ingest, Clean, Schema Infer, Load)
        prep = run_pipeline(scenario['files'])
        if prep is False:
            print("  ❌ FAIL: Data ingestion or cleaning failed.")
            continue
        
        schemas, cleaning_reports, conn = prep
        
        # Step 3: LLM Planning
        plan = plan_and_generate(schemas, scenario['question'])
        
        if plan["feasible"] != scenario["expect_feasible"]:
            print(f"  ❌ FAIL: Expected feasible={scenario['expect_feasible']}, got {plan['feasible']}.")
            if not plan["feasible"]:
                print(f"     Reason: {plan.get('reason')}")
            continue
            
        if not plan["feasible"]:
            # If we expected it to fail (e.g., Guardrail test) and it did, that's a pass!
            print("  ✅ PASS: Query correctly flagged as infeasible/blocked.")
            passed += 1
            continue

        # Step 4: Validate SQL
        sql = plan["sql"]
        validation = validate_sql(sql, schemas, plan.get("tables_used"))
        if not validation["valid"]:
            print(f"  ❌ FAIL: Generated SQL failed validation.")
            print(f"     SQL: {sql}")
            print(f"     Reason: {validation['reason']}")
            continue

        # Step 5: Execution
        outcome = run_query(sql, conn)
        if not outcome["success"]:
            print(f"  ❌ FAIL: SQL Execution error in DuckDB.")
            print(f"     SQL: {sql}")
            print(f"     Error: {outcome['error']}")
            continue

        # If it made it here, the pipeline successfully understood, planned, and executed!
        print(f"  ✅ PASS: Successfully generated and executed SQL.")
        print(f"     Returned {len(outcome['result'])} rows.")
        passed += 1

    print("\n" + "="*60)
    print(f"🏁 Test Suite Completed: {passed}/{total} Passed")
    print("="*60)

if __name__ == "__main__":
    run_tests()