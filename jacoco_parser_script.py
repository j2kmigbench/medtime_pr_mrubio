import json
import os
import subprocess
import xml.etree.ElementTree as ET
import pandas as pd
import re
import sys

REPO_PATH = sys.argv[1]
if REPO_PATH:
    TEST_DIR = os.path.join(REPO_PATH, "app", "src", "test")

def get_modified_sources(base_sha, head_sha):
    cmd = subprocess.run(
        ["git", "diff", "--name-only", base_sha, head_sha], 
        cwd=REPO_PATH, capture_output=True, text=True, check=True
    )
    files = [line.strip() for line in cmd.stdout.splitlines() if line.strip()]
    
    modified_source_files = []
    for file in files:
        if file.startswith("app/src/main/java/") or file.startswith("app/src/main/kotlin/"):
            if file.endswith(".kt") or file.endswith(".java"):
                clean_key = re.sub(r"^app/src/main/(java|kotlin)/", "", file)
                clean_key = re.sub(r"\.(java|kt)$", "", clean_key)
                modified_source_files.append(clean_key)
    return modified_source_files

def build_test_files_lookup(test_directory):
    lookup = {}
    if not os.path.exists(test_directory):
        return lookup
        
    for root_dir, _, files in os.walk(test_directory):
        for f in files:
            if f.endswith("Test.java") or f.endswith("Test.kt"):
                lookup[f] = os.path.join(root_dir, f)
    return lookup

def parse_jacoco_xml(xml_path, metrics_dict):
    if not os.path.exists(xml_path):
        return
        
    tree = ET.parse(xml_path)
    root = tree.getroot()

    for package in root.findall("package"):
        for class_node in package.findall(".//class"):
            class_name = class_node.get('name')
            
            matching_keys = [k for k in metrics_dict if class_name == k or class_name.startswith(k + "$")]
            if not matching_keys:
                continue
                
            for key in matching_keys:
                for counter in class_node.findall('counter'):
                    ctype = counter.get('type')
                    covered = int(counter.get("covered", 0))
                    missed = int(counter.get("missed", 0))
                    
                    if ctype == "LINE":
                        metrics_dict[key]["lines_covered"] += covered
                        metrics_dict[key]["lines_missed"] += missed
                    elif ctype == "BRANCH":
                        metrics_dict[key]["branches_covered"] += covered
                        metrics_dict[key]["branches_missed"] += missed

def main():
    with open('build_results.json', "r") as file:
        results_data = json.load(file)

    test_files_lookup = build_test_files_lookup(TEST_DIR)
    parser_results = []
    rows = []

    for item in results_data.get("prs", []):
        pr_number = item["pr_number"]
        base_sha = item["base_sha_full"]
        head_sha = item["head_sha_full"]
        print(f"Starting PR #{pr_number}")

        modified_sources = get_modified_sources(base_sha, head_sha)
        file_metrics = {
            key: {"lines_covered": 0, "lines_missed": 0, "branches_covered": 0, "branches_missed": 0}
            for key in modified_sources
        }

        if item.get("coverage_xml_extracted"):
            parse_jacoco_xml(f"./reports/pr_{pr_number}/jacoco.xml", file_metrics)

        modified_files_result = []
        
        for key, metrics in file_metrics.items():
            lines_covered = metrics["lines_covered"]
            lines_missed = metrics["lines_missed"]
            total_lines = lines_covered + lines_missed
            line_cov_pct = (lines_covered / total_lines) * 100 if total_lines > 0 else 0.0

            class_name_strip = os.path.basename(key)
            test_kt_name = f"{class_name_strip}Test.kt"
            test_java_name = f"{class_name_strip}Test.java"

            test_file = test_files_lookup.get(test_kt_name) or test_files_lookup.get(test_java_name)
            test_file = os.path.relpath(test_file, REPO_PATH) if test_file else None

            child_result = {
                "file_path": key,
                "lines_covered": lines_covered,
                "lines_missed": lines_missed,
                "line_coverage_percentage": round(line_cov_pct, 2),
                "branches_covered": metrics["branches_covered"],
                "branches_missed": metrics["branches_missed"],
                "has_corresponding_test_file": test_file is not None,
                "test_file_path": test_file
            }
            modified_files_result.append(child_result)
            rows.append({"pr_number": pr_number, "base_sha_full": base_sha, **child_result})

        if not modified_sources:
            rows.append({
                "pr_number": pr_number,
                "base_sha_full": base_sha,
                "file_path": "N/A (No Java/Kotlin source modified)",
                "lines_covered": 0, "lines_missed": 0, "line_coverage_percentage": 0.0,
                "branches_covered": 0, "branches_missed": 0,
                "has_corresponding_test_file": False, "test_file_path": None
            })

        parser_results.append({
            "pr_number": pr_number,
            "base_sha_full": base_sha,
            "modified_files": modified_files_result
        })

    df = pd.DataFrame(rows)
    cols = [
    "pr_number", 
    "base_sha_full", 
    "file_path", 
    "lines_covered", 
    "lines_missed", 
    "line_coverage_percentage", 
    "branches_covered", 
    "branches_missed", 
    "has_corresponding_test_file", 
    "test_file_path"
    ]
    existing_cols = [c for c in cols if c in df.columns]
    df = df[existing_cols]

    with open('medtimer-coverage-results.json', 'w') as file:
        json.dump({"prs": parser_results}, file, indent=2)

    with pd.ExcelWriter("medtimer-coverage-reports.xlsx", engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="medTimer", index=False)

    print("Jacoco parsing completed successfully.")

if __name__ == "__main__":
    main()