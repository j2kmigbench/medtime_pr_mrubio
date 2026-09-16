import json
import subprocess

with open('medtimer-migration-prs.json', 'r') as f:
    prs_data = json.load(f)
    sha_map = {item["pr_number"]: item["base_sha_full"] for item in prs_data["prs"]}

with open('build_results.json', 'r') as file:
    data = json.load(file)

push_results = []

for item in data:
    warnings = []
    pr_number = item["pr_number"]
    base_sha_full = sha_map.get(pr_number)
    if not base_sha_full:
                warnings.append(f"PR #{pr_number} not found in SHA mapping file")
    git_result = item["git_result"]
    network_result = item["network_result"]
    size = item["image_size"]
    ghcr_result = False

    if(git_result and network_result and base_sha_full):
        short_sha = base_sha_full[:7]
        local_tag = f"futsch1__medtimer:pr-{pr_number}-base-{short_sha}"
        remote_tag = f"ghcr.io/j2kmigbench/{local_tag}"

        try:
            subprocess.run(["docker", "tag", local_tag, remote_tag], check=True)
            subprocess.run(["docker", "push", remote_tag], check=True)
            ghcr_result = True
        except subprocess.CalledProcessError:
            warnings.append("Docker tagging or GHCR push failed during execution")
            ghcr_result = False
    else:
        warnings.append("GHCR push skipped due to verification failure")
    if not git_result:
        warnings.append("Git history stripping failed (more than 1 commit found)")
    if not network_result:
        warnings.append("Offline build failed under --network none")

    push_result = {
        "pr_number": pr_number,
        "base_sha_full": base_sha_full,
        "image_size": size,
        "git_result": git_result,
        "network_result": network_result,
        "ghcr_result": ghcr_result,
        "warnings": warnings
    }
    push_results.append(push_result)

with open('build_results.json', 'w') as file:
    json.dump(push_results, file, indent=2)

print("Image tagging and GHCR push completed. Results in build_results.json.")