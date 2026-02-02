#!/usr/bin/env bash
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Usage
usage() {
    echo "Usage: $0 <version>"
    echo ""
    echo "Example: $0 0.7.0"
    echo ""
    echo "This script will:"
    echo "  1. Validate version format (semver)"
    echo "  2. Check you're on main branch"
    echo "  3. Check working directory is clean"
    echo "  4. Update version in pyproject.toml and package.json"
    echo "  5. Prompt you to update CHANGELOG.md"
    echo "  6. Commit, tag, and push"
    echo ""
    echo "The CI will then:"
    echo "  - Validate version matches tag"
    echo "  - Build and publish to PyPI"
    echo "  - Create GitHub release from CHANGELOG"
    exit 1
}

# Validate semver format
validate_version() {
    local version=$1
    if [[ ! $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo -e "${RED}Error: Invalid version format '$version'${NC}"
        echo "Expected: MAJOR.MINOR.PATCH (e.g., 0.7.0)"
        exit 1
    fi
}

# Check branch
check_branch() {
    local branch
    branch=$(git rev-parse --abbrev-ref HEAD)
    if [[ $branch != "main" ]]; then
        echo -e "${YELLOW}Warning: You're on branch '$branch', not 'main'${NC}"
        read -p "Continue anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Check working directory
check_clean() {
    if [[ -n $(git status --porcelain) ]]; then
        echo -e "${RED}Error: Working directory is not clean${NC}"
        echo "Commit or stash your changes first."
        git status --short
        exit 1
    fi
}

# Update pyproject.toml version
update_version() {
    local version=$1
    local current
    current=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")

    echo -e "Current version: ${YELLOW}$current${NC}"
    echo -e "New version:     ${GREEN}$version${NC}"

    # Use sed to update version
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/^version = \".*\"/version = \"$version\"/" pyproject.toml
    else
        sed -i "s/^version = \".*\"/version = \"$version\"/" pyproject.toml
    fi

    # Verify update
    local updated
    updated=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])")
    if [[ $updated != "$version" ]]; then
        echo -e "${RED}Error: Failed to update version in pyproject.toml${NC}"
        exit 1
    fi
    echo -e "${GREEN}Updated pyproject.toml${NC}"
}

# Update npm package version
update_npm_version() {
    local version=$1
    local npm_pkg="packages/buildlog-npm/package.json"
    if [[ -f "$npm_pkg" ]]; then
        npm version "$version" --no-git-tag-version --prefix packages/buildlog-npm
        echo -e "${GREEN}Updated $npm_pkg${NC}"
    else
        echo -e "${YELLOW}Warning: $npm_pkg not found, skipping npm version bump${NC}"
    fi
}

# Check CHANGELOG has entry
check_changelog() {
    local version=$1
    if ! grep -q "## \[$version\]" CHANGELOG.md; then
        echo -e "${YELLOW}CHANGELOG.md doesn't have an entry for [$version]${NC}"
        echo ""
        echo "Please add release notes under [Unreleased] or create a new section."
        echo "Opening CHANGELOG.md..."
        echo ""
        ${EDITOR:-vim} CHANGELOG.md

        # Re-check after editing
        if ! grep -q "## \[$version\]" CHANGELOG.md; then
            echo -e "${RED}Error: Still no CHANGELOG entry for [$version]${NC}"
            echo "You need to rename [Unreleased] to [$version] or add a new section."
            exit 1
        fi
    fi
    echo -e "${GREEN}CHANGELOG.md has entry for [$version]${NC}"
}

# Update CHANGELOG links
update_changelog_links() {
    local version=$1
    local prev_version
    prev_version=$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')

    # Add new Unreleased section if needed
    if ! grep -q "## \[Unreleased\]" CHANGELOG.md; then
        # Insert after the header
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "/^## \[$version\]/i\\
\\
## [Unreleased]\\
" CHANGELOG.md
        else
            sed -i "/^## \[$version\]/i\\\n## [Unreleased]\n" CHANGELOG.md
        fi
    fi

    # Update the links at the bottom
    if ! grep -q "^\[Unreleased\]:.*v$version" CHANGELOG.md; then
        # Update Unreleased link
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|\[Unreleased\]:.*|[Unreleased]: https://github.com/Peleke/buildlog-template/compare/v$version...HEAD|" CHANGELOG.md
        else
            sed -i "s|\[Unreleased\]:.*|[Unreleased]: https://github.com/Peleke/buildlog-template/compare/v$version...HEAD|" CHANGELOG.md
        fi

        # Add new version link if not present
        if ! grep -q "^\[$version\]:" CHANGELOG.md; then
            # Insert after Unreleased link
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "/^\[Unreleased\]:/a\\
[$version]: https://github.com/Peleke/buildlog-template/compare/v$prev_version...v$version
" CHANGELOG.md
            else
                sed -i "/^\[Unreleased\]:/a[$version]: https://github.com/Peleke/buildlog-template/compare/v$prev_version...v$version" CHANGELOG.md
            fi
        fi
    fi
}

# Main
main() {
    if [[ $# -ne 1 ]]; then
        usage
    fi

    local version=$1

    echo "=========================================="
    echo "  buildlog release script"
    echo "=========================================="
    echo ""

    # Validations
    validate_version "$version"
    check_branch
    check_clean

    # Updates
    update_version "$version"
    update_npm_version "$version"
    check_changelog "$version"
    update_changelog_links "$version"

    # Show diff
    echo ""
    echo "Changes to be committed:"
    git diff --stat
    echo ""

    # Confirm
    read -p "Commit, tag v$version, and push? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborting. Changes are staged but not committed."
        git checkout -- pyproject.toml CHANGELOG.md
        exit 1
    fi

    # Commit and tag
    git add pyproject.toml CHANGELOG.md packages/buildlog-npm/package.json
    git commit -m "release: v$version"
    git tag "v$version"

    # Push
    echo ""
    echo -e "${GREEN}Pushing to origin...${NC}"
    git push origin main
    git push origin "v$version"

    echo ""
    echo -e "${GREEN}=========================================="
    echo "  Release v$version initiated!"
    echo "==========================================${NC}"
    echo ""
    echo "CI will now:"
    echo "  1. Validate version matches tag"
    echo "  2. Run tests"
    echo "  3. Build and publish to PyPI"
    echo "  4. Publish npm package"
    echo "  5. Create GitHub release"
    echo ""
    echo "Monitor progress:"
    echo "  https://github.com/Peleke/buildlog-template/actions"
}

main "$@"
