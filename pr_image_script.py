import json
import subprocess
import os
import textwrap

with open('medtimer-migration-prs.json', 'r') as file:
    data = json.load(file)
    final_results = []
    for item in data["prs"]:
        #Metadata Extraction
        pr_number = item["pr_number"]
        base_sha = item["base_sha_full"]
        short_sha = item["base_sha_full"][:7]

        tag = f"futsch1__medtimer:pr-{pr_number}-base-{short_sha}"
        dockerfile_content = textwrap.dedent(f"""
            FROM medtimer-shared:latest

            WORKDIR /workspace/repo

            RUN git checkout {base_sha} && \
                rm -rf .git && \
                git init -q && \
                git config user.email "bench@j2kmigbench.org" && \
                git config user.name "J2KBench" && \
                git add -A && \
                git commit -q -m "base state"
                
            RUN chmod +x ./gradlew && \
                ./gradlew --no-daemon assembleDebug
            """)
        with open('Dockerfile.tmp', 'w') as file:
            file.write(dockerfile_content)

        try:
            subprocess.run(["docker", "build", "-t", f"{tag}", "-f", "Dockerfile.tmp", "."], check=True)
        finally:
            if(os.path.exists('Dockerfile.tmp')):
                os.remove('Dockerfile.tmp')


        #Verification Checks
        gitCheck = ["docker", "run", "--rm", f"{tag}", "git", "log", "--all", "--oneline"]
        gitResult = subprocess.run(gitCheck, capture_output=True, text=True)
        lines = [line for line in gitResult.stdout.strip().splitlines() if line]
        is_single_commit = (len(lines) == 1)

        networkCheck = ["docker", "run", "--rm", "--network", "none", f"{tag}", "./gradlew", "assembleDebug", "--no-build-cache", "--rerun-tasks"]
        networkResult = subprocess.run(networkCheck, capture_output=True, text=True)

        pr_result = {
            "pr_number": pr_number,
            "image_size": subprocess.run(["docker", "image", "inspect", tag, "--format={{.Size}}"], capture_output=True, text=True).stdout.strip(),
            "git_result": is_single_commit,
            "network_result": networkResult.returncode == 0
        }
        final_results.append(pr_result)

with open('build_results.json', 'w') as file:
    json.dump(final_results, file, indent=2)

print("Image build and verification completed successfully. Results saved to build_results.json.")