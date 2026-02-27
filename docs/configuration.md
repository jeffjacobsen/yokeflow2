# Configuration Guide

YokeFlow supports YAML configuration files for managing default settings. Configuration is primarily managed through the Web UI, but YAML files provide defaults.

## Quick Start

1. **Copy the example config:**
   ```bash
   cp .yokeflow.yaml.example .yokeflow.yaml
   ```

2. **Edit settings** in `.yokeflow.yaml`

3. **Settings are used by:** Web UI, API endpoints, and utility scripts

## Configuration File Locations

The system looks for configuration files in this order:

1. **Current directory**: `.yokeflow.yaml` — project-specific settings
2. **Home directory**: `~/.yokeflow.yaml` — global defaults
3. **Built-in defaults** — see [server/utils/config.py](../server/utils/config.py)

Web UI settings (selected during project creation) override config file defaults.

## Configuration Options

### Models

Control which Claude models are used for different session types:

```yaml
models:
  initializer: claude-opus-4-6        # For planning/initialization
  coding: claude-sonnet-4-6           # For implementation
  review: claude-sonnet-4-6           # For quality reviews
  prompt_improvement: claude-opus-4-6 # For prompt analysis
```

**Recommended:**
- **Opus** for initialization (better planning capabilities)
- **Sonnet** for coding (faster, more cost-effective)
- **Sonnet** for reviews (good analysis at lower cost)
- **Opus** for prompt improvements (critical reasoning task)

### Timing

```yaml
timing:
  auto_continue_delay: 3      # Seconds between sessions
  web_ui_poll_interval: 5     # Web UI refresh interval
  web_ui_port: 3010           # Web dashboard port
```

### Security

Add custom blocked commands:

```yaml
security:
  additional_blocked_commands:
    - my-dangerous-script
    - custom-deploy-tool
```

These are added to the built-in blocklist in [server/utils/security.py](../server/utils/security.py).

### Project

```yaml
project:
  default_projects_dir: projects   # Where to store projects
  max_iterations: null             # Iteration limit (null = unlimited)
```

### Brownfield

Settings for importing existing codebases:

```yaml
brownfield:
  default_feature_branch_prefix: yokeflow/
  run_existing_tests_before_changes: true
  run_existing_tests_after_changes: true
```

### Spec Pre-Analysis

Optional pre-analysis of spec files with a fast model before initialization. Useful for large or multi-file specifications.

```yaml
spec_analysis:
  enabled: false
  model: claude-haiku-4-5-20251001
```

## Priority Order

Settings are applied in this order (highest priority first):

1. **Web UI selections** — model dropdowns, project-specific settings
2. **Configuration file** — `.yokeflow.yaml`
3. **Environment variables** — `.env` file
4. **Built-in defaults**

## Examples

### Basic Config

```yaml
models:
  initializer: claude-opus-4-6
  coding: claude-sonnet-4-6

timing:
  auto_continue_delay: 5

project:
  default_projects_dir: projects
```

### Complete Config

See [.yokeflow.yaml.example](../.yokeflow.yaml.example) for a complete configuration file with all available options and comments.

## Validation

The config system validates settings on load:

- Invalid YAML — error message shown in logs
- Missing file — uses built-in defaults
- Invalid model names — passed through (API will validate)

## Best Practices

1. **Use global config** (`~/.yokeflow.yaml`) for personal defaults
2. **Use local config** (`.yokeflow.yaml`) for project-specific needs
3. **Add to .gitignore** if config contains sensitive paths

## See Also

- [server/utils/config.py](../server/utils/config.py) — Configuration implementation
- [.yokeflow.yaml.example](../.yokeflow.yaml.example) — Full example with comments
- [quality-system.md](quality-system.md) — Quality system documentation
- [developer-guide.md](developer-guide.md) — Platform architecture
