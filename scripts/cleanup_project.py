#!/usr/bin/env python3
"""
Utility script to forcefully clean up a project directory.

This handles cases where normal deletion fails due to permission issues,
typically when node_modules or other files were created inside Docker containers.

Usage:
    python scripts/cleanup_project.py <project_name>
    python scripts/cleanup_project.py --all  # Clean all projects with permission issues
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
import os


def cleanup_with_docker(path: Path) -> bool:
    """
    Use Docker to remove a directory with root permissions.

    This is needed when files were created inside Docker containers
    and have root ownership.
    """
    if not path.exists():
        print(f"Path does not exist: {path}")
        return True

    print(f"Attempting Docker-based removal of {path}")

    try:
        # Use Alpine Linux container to remove with root permissions
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{path.absolute()}:/workspace",
            "alpine:latest",
            "rm", "-rf", "/workspace"
        ]

        result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            # Docker removed the contents, now try to remove the empty directory
            if path.exists():
                try:
                    path.rmdir()
                except:
                    # Directory might have more files, try rmtree with ignore_errors
                    shutil.rmtree(path, ignore_errors=True)

            print(f"✅ Successfully removed {path} using Docker")
            return True
        else:
            print(f"❌ Docker removal failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"❌ Docker removal timed out")
        return False
    except Exception as e:
        print(f"❌ Docker removal error: {e}")
        return False


def cleanup_project(project_name: str, projects_dir: Path) -> bool:
    """Clean up a single project directory."""
    project_path = projects_dir / project_name

    if not project_path.exists():
        print(f"Project directory does not exist: {project_path}")
        return True

    print(f"Cleaning up project: {project_name}")

    # First attempt: normal deletion
    try:
        shutil.rmtree(project_path)
        print(f"✅ Successfully removed {project_path}")
        return True
    except PermissionError as e:
        print(f"⚠️  Permission denied: {e}")
        print("Attempting Docker-based removal...")

        # Second attempt: Docker-based removal
        if cleanup_with_docker(project_path):
            return True

        # Final attempt: ignore errors
        print("Attempting removal with ignore_errors...")
        shutil.rmtree(project_path, ignore_errors=True)

        if project_path.exists():
            print(f"⚠️  Partial removal - some files may remain in {project_path}")
            print("You may need to manually run: sudo rm -rf " + str(project_path))
            return False
        else:
            print(f"✅ Successfully removed {project_path} (with ignored errors)")
            return True


def find_problem_projects(projects_dir: Path) -> list:
    """Find projects with permission issues."""
    problem_projects = []

    if not projects_dir.exists():
        return problem_projects

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        # Check for common problem directories
        node_modules = project_dir / "frontend" / "node_modules"
        if node_modules.exists():
            # Try to check permissions
            try:
                # Try to list directory
                list(node_modules.iterdir())
            except PermissionError:
                problem_projects.append(project_dir.name)
                continue

            # Try to check if we can delete a test file
            test_file = node_modules / ".test_permission"
            try:
                test_file.touch()
                test_file.unlink()
            except PermissionError:
                problem_projects.append(project_dir.name)

    return problem_projects


def main():
    parser = argparse.ArgumentParser(description="Clean up YokeFlow project directories")
    parser.add_argument("project", nargs="?", help="Project name to clean up")
    parser.add_argument("--all", action="store_true", help="Clean all projects with permission issues")
    parser.add_argument("--projects-dir", default="projects", help="Path to projects directory")
    parser.add_argument("--force", action="store_true", help="Force removal even if Docker is not available")

    args = parser.parse_args()

    projects_dir = Path(args.projects_dir)

    if not projects_dir.exists():
        print(f"Projects directory does not exist: {projects_dir}")
        sys.exit(1)

    # Check if Docker is available
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        docker_available = True
    except:
        docker_available = False
        if not args.force:
            print("❌ Docker is not available. Docker is needed to clean up files created with root permissions.")
            print("   Install Docker or use --force to attempt cleanup without it.")
            sys.exit(1)

    if args.all:
        # Find and clean all problem projects
        problem_projects = find_problem_projects(projects_dir)

        if not problem_projects:
            print("✅ No projects with permission issues found")
            return

        print(f"Found {len(problem_projects)} project(s) with potential permission issues:")
        for project in problem_projects:
            print(f"  - {project}")

        response = input("\nProceed with cleanup? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return

        success_count = 0
        for project in problem_projects:
            if cleanup_project(project, projects_dir):
                success_count += 1
            print()

        print(f"Cleaned {success_count}/{len(problem_projects)} projects")

    elif args.project:
        # Clean specific project
        if cleanup_project(args.project, projects_dir):
            print(f"✅ Successfully cleaned up {args.project}")
        else:
            print(f"⚠️  Cleanup incomplete for {args.project}")
            sys.exit(1)
    else:
        # List available projects
        projects = [d.name for d in projects_dir.iterdir() if d.is_dir()]

        if not projects:
            print("No projects found in projects directory")
            return

        print("Available projects:")
        for project in sorted(projects):
            project_path = projects_dir / project
            size = sum(f.stat().st_size for f in project_path.rglob('*') if f.is_file())
            size_mb = size / (1024 * 1024)
            print(f"  - {project:<30} ({size_mb:.1f} MB)")

        print(f"\nUsage: {sys.argv[0]} <project_name>")
        print(f"   or: {sys.argv[0]} --all")


if __name__ == "__main__":
    main()